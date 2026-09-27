#[path = "../study.rs"]
mod study;

use femtovg::{renderer::WGPURenderer, BlendFactor, Canvas, Color, Paint, Path};
use pipeline_cache_policy::Policy;
use std::{sync::Arc, time::Instant};

const FACTORS: [BlendFactor; 10] = [
    BlendFactor::Zero,
    BlendFactor::One,
    BlendFactor::SrcColor,
    BlendFactor::OneMinusSrcColor,
    BlendFactor::DstColor,
    BlendFactor::OneMinusDstColor,
    BlendFactor::SrcAlpha,
    BlendFactor::OneMinusSrcAlpha,
    BlendFactor::DstAlpha,
    BlendFactor::OneMinusDstAlpha,
];

fn main() {
    assert_eq!(
        option_env!("PIPELINE_POLICY_STUDY"),
        Some("1"),
        "build with femtovg-policy-study.py first"
    );
    let args: Vec<_> = std::env::args().collect();
    if args.get(1).is_some_and(|s| s == "--sweep") {
        for seed in 1..=10 {
            for scale in [64, 128, 256] {
                for scenario in study::SCENARIOS {
                    let trace = study::trace(scenario, scale, 100, seed);
                    for capacity in [32, 64, 128, 256, 512] {
                        for policy in study::POLICIES {
                            let (frames, stats) =
                                study::simulate(Policy::parse(policy), capacity, &trace);
                            println!(
                                "{}",
                                serde_json::json!({"seed":seed,"scale":scale,"scenario":scenario,
                    "capacity":capacity,"policy":policy,"stats":stats,"frames":frames.iter().map(|f|
                        serde_json::json!({"phase":f.phase,"misses":f.misses,"requests":f.requests,
                            "retained":f.retained,"ghost":f.ghost})).collect::<Vec<_>>()})
                            );
                        }
                    }
                }
            }
        }
        return;
    }
    assert_eq!(
        args.len(),
        7,
        "policy-study POLICY CAPACITY SCENARIO SCALE FRAMES SEED"
    );
    let policy = Policy::parse(&args[1]);
    let capacity = args[2].parse().unwrap();
    let scale = args[4].parse().unwrap();
    let count = args[5].parse().unwrap();
    let seed = args[6].parse().unwrap();
    let trace = study::trace(&args[3], scale, count, seed);
    assert!(trace
        .iter()
        .flat_map(|f| f.flushes.iter().flatten())
        .all(|&id| id <= 10_000));
    let (expected, stats) = study::simulate(policy, capacity, &trace);
    pipeline_cache_policy::configure(policy, capacity);
    let instance = wgpu::Instance::default();
    let adapter =
        pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions::default()))
            .expect("real GPU required");
    let info = adapter.get_info();
    #[cfg(target_os = "macos")]
    assert_eq!(info.backend, wgpu::Backend::Metal);
    let (device, queue) = pollster::block_on(adapter.request_device(&wgpu::DeviceDescriptor {
        required_limits: wgpu::Limits::downlevel_defaults().using_resolution(adapter.limits()),
        ..Default::default()
    }))
    .unwrap();
    device.on_uncaptured_error(Arc::new(|e| panic!("WGPU: {e}")));
    let target = device.create_texture(&wgpu::TextureDescriptor {
        label: Some("policy-study"),
        size: wgpu::Extent3d {
            width: 64,
            height: 64,
            depth_or_array_layers: 1,
        },
        mip_level_count: 1,
        sample_count: 1,
        dimension: wgpu::TextureDimension::D2,
        format: wgpu::TextureFormat::Rgba8Unorm,
        usage: wgpu::TextureUsages::RENDER_ATTACHMENT,
        view_formats: &[],
    });
    let mut canvas = Canvas::new(WGPURenderer::new(device.clone(), queue.clone())).unwrap();
    canvas.set_size(64, 64, 1.0);
    let mut rect = Path::new();
    rect.rect(4.0, 4.0, 32.0, 32.0);
    let paint = Paint::color(Color::rgb(200, 20, 40)).with_anti_alias(false);
    let mut results = Vec::with_capacity(trace.len());
    let initial_resource_bytes = metal_resource_bytes(&device);
    for (index, (frame, expected)) in trace.iter().zip(&expected).enumerate() {
        let mut flushes = Vec::with_capacity(frame.flushes.len());
        let start = Instant::now();
        for (commands, model) in frame.flushes.iter().zip(&expected.flushes) {
            let before = WGPURenderer::benchmark_pipeline_counts().0;
            for &id in commands {
                if id == 0 {
                    canvas.clear_rect(0, 0, 64, 64, Color::black());
                } else {
                    let n = id as usize - 1;
                    canvas.global_composite_blend_func_separate(
                        FACTORS[n % 10],
                        FACTORS[(n / 10) % 10],
                        FACTORS[(n / 100) % 10],
                        FACTORS[(n / 1000) % 10],
                    );
                    canvas.fill_path(&rect, &paint);
                }
            }
            queue.submit(canvas.flush_to_output(&target));
            let (total, retained) = WGPURenderer::benchmark_pipeline_counts();
            // Match every flush, including cold and transition frames; no silently skipped cases.
            assert_eq!(
                (total - before, retained),
                (model.misses, model.retained),
                "frame {index}: CPU/GPU policy mismatch"
            );
            flushes.push(serde_json::json!({"created":total-before,"retained":retained}));
        }
        let cpu_ms = start.elapsed().as_secs_f64() * 1000.0;
        device.poll(wgpu::PollType::wait_indefinitely()).unwrap();
        let completed_ms = start.elapsed().as_secs_f64() * 1000.0;
        let live = device.get_internal_counters().hal.render_pipelines.read();
        assert!(live > 0);
        results.push(serde_json::json!({"index":index,"phase":frame.phase,"cpu_ms":cpu_ms,"completed_ms":completed_ms,
            "flushes":flushes,"live_pipelines":live,"metal_resource_bytes":metal_resource_bytes(&device)}));
    }
    println!(
        "{}",
        serde_json::json!({"policy":args[1],"capacity":capacity,"scenario":args[3],"scale":scale,"seed":seed,
        "adapter":format!("{info:?}"),"initial_resource_bytes":initial_resource_bytes,"model_stats":stats,"frames":results})
    );
}

#[cfg(target_os = "macos")]
fn metal_resource_bytes(device: &wgpu::Device) -> Option<u64> {
    use objc2_metal::MTLDevice;
    // Read-only access while holding the HAL guard, as in the existing benchmark.
    let raw = unsafe { device.as_hal::<wgpu::hal::api::Metal>() }?;
    Some(raw.raw_device().currentAllocatedSize() as u64)
}
#[cfg(not(target_os = "macos"))]
fn metal_resource_bytes(_: &wgpu::Device) -> Option<u64> {
    None
}
