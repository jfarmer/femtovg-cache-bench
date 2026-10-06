//! Real-device, offscreen cache-pressure benchmark. No window, fonts, or icon loading.
use femtovg::{
    renderer::WGPURenderer, BlendFactor, Canvas, Color, DrawCommand, FillRule, GlyphDrawCommands,
    ImageFilter, ImageFlags, ImageId, LayerEffects, Paint, Path, PixelFormat, Quad,
};
use serde::Serialize;
use std::{sync::Arc, time::Instant};

const SIZE: u32 = 64;
const FACTORS: [BlendFactor; 10] = [
    BlendFactor::One,
    BlendFactor::OneMinusSrcAlpha,
    BlendFactor::Zero,
    BlendFactor::SrcColor,
    BlendFactor::OneMinusSrcColor,
    BlendFactor::DstColor,
    BlendFactor::OneMinusDstColor,
    BlendFactor::SrcAlpha,
    BlendFactor::DstAlpha,
    BlendFactor::OneMinusDstAlpha,
];

#[derive(Serialize)]
struct Flush {
    name: &'static str,
    cpu_ms: f64,
    created: u64,
    retained: usize,
}

#[derive(Serialize)]
struct Frame {
    phase: &'static str,
    /// Which part of a phased workload the frame belongs to; "steady" when the workload has one part.
    stage: &'static str,
    cpu_ms: f64,
    completed_ms: f64,
    live_pipelines: isize,
    metal_resource_bytes: Option<u64>,
    flushes: Vec<Flush>,
}

/// What one frame draws before its clear flush.
#[derive(Clone, Copy)]
enum Draw {
    Mixed,
    /// `count` pipelines including the clear pipeline, so `count - 1` blend states, numbered from `first`.
    States { first: usize, count: usize },
}

enum Workload {
    States(usize),
    Mixed,
    /// `a` pipelines for ten frames, then `b` different ones until ten frames before the end, then `a` again.
    /// Shows what each policy does with pipelines that go unused for a long run of flushes and then come back.
    Return { a: usize, b: usize },
    /// Every measured frame draws `k` blend states no earlier frame used. Shows how large each policy lets the
    /// cache grow under a stream of one-off states.
    Scan { k: usize },
}

struct Bench {
    device: wgpu::Device,
    queue: wgpu::Queue,
    target: wgpu::Texture,
    canvas: Canvas<WGPURenderer>,
    atlas: ImageId,
    rect: Path,
}

impl Bench {
    fn flush(&mut self, name: &'static str, start: Instant) -> Flush {
        let before = WGPURenderer::benchmark_pipeline_counts().0;
        self.queue.submit(self.canvas.flush_to_output(&self.target));
        let cpu_ms = start.elapsed().as_secs_f64() * 1000.0;
        let (created, retained) = WGPURenderer::benchmark_pipeline_counts();
        Flush {
            name,
            cpu_ms,
            created: created - before,
            retained,
        }
    }

    fn clear(&mut self) -> Flush {
        let start = Instant::now();
        self.canvas.clear_rect(0, 0, SIZE, SIZE, Color::black());
        self.flush("clear", start)
    }

    fn states(&mut self, first: usize, count: usize) -> Flush {
        let start = Instant::now();
        self.canvas.save();
        for i in first..first + count {
            // 200 distinct valid blend states, then 1,400 more that also vary the destination alpha factor.
            // Alpha factors also contribute to the pipeline key. Index 1600 would repeat index 0.
            assert!(i < 1600, "the blend-state generator holds 1600 distinct states");
            self.canvas.global_composite_blend_func_separate(
                FACTORS[i % 10],
                FACTORS[(i / 10) % 10],
                if i % 200 < 100 {
                    BlendFactor::One
                } else {
                    BlendFactor::Zero
                },
                if i < 200 {
                    BlendFactor::OneMinusSrcAlpha
                } else {
                    FACTORS[(2 + i / 200) % 10]
                },
            );
            self.canvas.fill_path(
                &self.rect,
                &Paint::color(Color::rgb(200, 20, 40)).with_anti_alias(false),
            );
        }
        self.canvas.restore();
        self.flush("states", start)
    }

    fn mixed(&mut self, flushes: &mut Vec<Flush>) {
        let red = Paint::color(Color::rgb(220, 30, 20));
        let blue = Paint::color(Color::rgb(20, 30, 220));
        let start = Instant::now();
        self.canvas.draw_glyph_commands(
            GlyphDrawCommands {
                alpha_glyphs: vec![DrawCommand {
                    image_id: self.atlas,
                    quads: vec![Quad {
                        x0: 8.0,
                        y0: 8.0,
                        x1: 16.0,
                        y1: 16.0,
                        s0: 0.0,
                        t0: 0.0,
                        s1: 1.0,
                        t1: 1.0,
                    }],
                }],
                color_glyphs: Vec::new(),
            },
            &red,
        );
        flushes.push(self.flush("glyph", start));

        let start = Instant::now();
        let mut clip = Path::new();
        clip.circle(24.0, 24.0, 18.0);
        self.canvas.save();
        self.canvas.clip_path(&clip, FillRule::NonZero);
        assert!(self
            .canvas
            .begin_layer(&LayerEffects::new().with_opacity(0.5)));
        self.canvas.fill_path(&self.rect, &red);
        self.canvas.end_layer();
        self.canvas.restore();
        flushes.push(self.flush("clipped-layer", start));

        let start = Instant::now();
        assert!(self.canvas.begin_layer(
            &LayerEffects::new().with_filters(&[ImageFilter::GaussianBlur { sigma: 3.0 }])
        ));
        self.canvas.fill_path(&self.rect, &blue);
        self.canvas.end_layer();
        flushes.push(self.flush("filter", start));

        let start = Instant::now();
        self.canvas.clear_rect(0, 0, SIZE, SIZE, Color::white());
        self.canvas.fill_path(&self.rect, &red);
        self.canvas.fill_path(
            &clip,
            &Paint::linear_gradient(0.0, 0.0, 40.0, 40.0, Color::white(), Color::black()),
        );
        self.canvas.stroke_path(&clip, &blue.with_line_width(3.0));
        self.canvas.save();
        self.canvas.scissor(0.0, 0.0, 30.0, 30.0);
        let mut concave = Path::new();
        concave.move_to(0.0, 0.0);
        concave.line_to(30.0, 30.0);
        concave.line_to(0.0, 30.0);
        concave.line_to(30.0, 0.0);
        concave.close();
        self.canvas
            .fill_path(&concave, &Paint::color(Color::rgb(20, 220, 30)));
        self.canvas.restore();
        flushes.push(self.flush("screen", start));
    }

    fn frame(&mut self, draw: Draw, phase: &'static str, stage: &'static str) -> Frame {
        let mut flushes = Vec::with_capacity(5);
        let start = Instant::now();
        match draw {
            // Include the distinct clear pipeline in the advertised working-set size.
            Draw::States { first, count } => flushes.push(self.states(first, count - 1)),
            Draw::Mixed => self.mixed(&mut flushes),
        }
        flushes.push(self.clear());
        let cpu_ms = start.elapsed().as_secs_f64() * 1000.0;
        self.device
            .poll(wgpu::PollType::wait_indefinitely())
            .unwrap();
        let completed_ms = start.elapsed().as_secs_f64() * 1000.0;
        // Diagnostics outside the measured interval. Live HAL objects can outlive cache entries.
        let live_pipelines = self
            .device
            .get_internal_counters()
            .hal
            .render_pipelines
            .read();
        assert!(live_pipelines > 0, "WGPU counters must be enabled");
        Frame {
            phase,
            stage,
            cpu_ms,
            completed_ms,
            live_pipelines,
            metal_resource_bytes: metal_resource_bytes(&self.device),
            flushes,
        }
    }
}

#[cfg(target_os = "macos")]
fn metal_resource_bytes(device: &wgpu::Device) -> Option<u64> {
    use objc2_metal::MTLDevice;
    // Hold the HAL guard for the read; no raw handle is changed or destroyed.
    let raw = unsafe { device.as_hal::<wgpu::hal::api::Metal>() }?;
    Some(raw.raw_device().currentAllocatedSize() as u64)
}

#[cfg(not(target_os = "macos"))]
fn metal_resource_bytes(_: &wgpu::Device) -> Option<u64> {
    None
}

fn main() {
    let args: Vec<_> = std::env::args().collect();
    assert_eq!(
        args.len(),
        4,
        "usage: femtovg-cache-bench POLICY STATES|mixed|return:A:B|scan:K FRAMES"
    );
    let policy = &args[1];
    assert_eq!(
        policy,
        option_env!("CACHE_BENCH_POLICY").unwrap_or("upstream"),
        "binary/policy mismatch"
    );
    let scenario = &args[2];
    let frames: usize = args[3].parse().unwrap();
    assert!(frames > 0);
    let workload = if scenario == "mixed" {
        Workload::Mixed
    } else if let Some(sizes) = scenario.strip_prefix("return:") {
        let (a, b) = sizes.split_once(':').expect("return:A:B");
        let (a, b) = (a.parse().unwrap(), b.parse().unwrap());
        // The two sets share only the clear pipeline, so the generator must hold a + b - 1 states.
        assert!(a >= 2 && b >= 2 && a + b - 1 <= 201, "return:A:B needs 2 <= A, B and A + B - 1 <= 201");
        assert!(frames >= 21, "return:A:B needs at least 21 frames: ten before, one or more away, ten after");
        Workload::Return { a, b }
    } else if let Some(k) = scenario.strip_prefix("scan:") {
        let k: usize = k.parse().unwrap();
        assert!(k >= 1 && (frames + 1) * k < 1600, "scan:K needs (FRAMES + 1) * K below 1600");
        Workload::Scan { k }
    } else {
        let n = scenario.parse::<usize>().unwrap();
        assert!((2..=201).contains(&n));
        Workload::States(n)
    };
    let steady = match workload {
        Workload::States(count) | Workload::Return { a: count, .. } => Draw::States { first: 0, count },
        Workload::Scan { k } => Draw::States { first: 0, count: k + 1 },
        Workload::Mixed => Draw::Mixed,
    };
    let instance = wgpu::Instance::default();
    let adapter =
        pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions::default()))
            .expect("real GPU adapter required");
    let info = adapter.get_info();
    #[cfg(target_os = "macos")]
    assert_eq!(info.backend, wgpu::Backend::Metal);
    let (device, queue) = pollster::block_on(adapter.request_device(&wgpu::DeviceDescriptor {
        required_limits: wgpu::Limits::downlevel_defaults().using_resolution(adapter.limits()),
        ..Default::default()
    }))
    .unwrap();
    device.on_uncaptured_error(Arc::new(|error| panic!("WGPU validation: {error}")));
    let target = device.create_texture(&wgpu::TextureDescriptor {
        label: Some("synthetic-cache-target"),
        size: wgpu::Extent3d {
            width: SIZE,
            height: SIZE,
            depth_or_array_layers: 1,
        },
        mip_level_count: 1,
        sample_count: 1,
        dimension: wgpu::TextureDimension::D2,
        format: wgpu::TextureFormat::Rgba8Unorm,
        usage: wgpu::TextureUsages::RENDER_ATTACHMENT | wgpu::TextureUsages::COPY_SRC,
        view_formats: &[],
    });
    let mut canvas = Canvas::new(WGPURenderer::new(device.clone(), queue.clone())).unwrap();
    canvas.set_size(SIZE, SIZE, 1.0);
    let atlas = canvas
        .create_image_empty(8, 8, PixelFormat::Gray8, ImageFlags::empty())
        .unwrap();
    let mut rect = Path::new();
    rect.rect(4.0, 4.0, 32.0, 32.0);
    let mut bench = Bench {
        device,
        queue,
        target,
        canvas,
        atlas,
        rect,
    };
    let before_resource_bytes = metal_resource_bytes(&bench.device);
    let mut results = Vec::with_capacity(frames + 6);
    results.push(bench.frame(steady, "cold", "steady"));
    if let Draw::States { count, .. } = steady {
        assert_eq!(
            results[0].flushes.iter().map(|f| f.created).sum::<u64>(),
            count as u64,
            "working-set size must match actual materializations"
        );
    }
    for _ in 0..5 {
        results.push(bench.frame(steady, "warmup", "steady"));
    }
    for index in 0..frames {
        let (draw, stage) = match workload {
            Workload::Return { a, b } => {
                // The away set starts where the first set's blend states end, so the two sets differ.
                let away = Draw::States { first: a - 1, count: b };
                if index < 10 {
                    (steady, "before")
                } else if index < frames - 10 {
                    (away, "away")
                } else if index == frames - 10 {
                    (steady, "return")
                } else {
                    (steady, "after")
                }
            }
            // The cold and warm-up frames used states 0..k, so the first measured frame starts at k.
            Workload::Scan { k } => (Draw::States { first: (index + 1) * k, count: k + 1 }, "scan"),
            _ => (steady, "steady"),
        };
        results.push(bench.frame(draw, "measured", stage));
    }
    let mut usage = std::mem::MaybeUninit::<libc::rusage>::uninit();
    // getrusage initializes the buffer on success. macOS reports bytes, Linux reports KiB.
    assert_eq!(
        unsafe { libc::getrusage(libc::RUSAGE_SELF, usage.as_mut_ptr()) },
        0
    );
    let usage = unsafe { usage.assume_init() };
    let peak_rss_bytes = usage.ru_maxrss as u64 * if cfg!(target_os = "macos") { 1 } else { 1024 };
    println!(
        "{}",
        serde_json::json!({
            "policy": policy, "scenario": scenario, "adapter": format!("{info:?}"),
            "before_resource_bytes": before_resource_bytes, "peak_rss_bytes": peak_rss_bytes,
            "frames": results,
        })
    );
}
