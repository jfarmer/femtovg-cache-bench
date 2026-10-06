// Times wgpu 30 render pipeline creation with femtovg's shader and pipeline layout.
use std::sync::Arc;
use std::time::{Duration, Instant};

const FACTORS: [wgpu::BlendFactor; 11] = [
    wgpu::BlendFactor::Zero,
    wgpu::BlendFactor::One,
    wgpu::BlendFactor::Src,
    wgpu::BlendFactor::OneMinusSrc,
    wgpu::BlendFactor::Dst,
    wgpu::BlendFactor::OneMinusDst,
    wgpu::BlendFactor::SrcAlpha,
    wgpu::BlendFactor::OneMinusSrcAlpha,
    wgpu::BlendFactor::DstAlpha,
    wgpu::BlendFactor::OneMinusDstAlpha,
    wgpu::BlendFactor::SrcAlphaSaturated,
];

fn blend(i: usize) -> wgpu::BlendState {
    let c = wgpu::BlendComponent {
        src_factor: FACTORS[i % 11],
        dst_factor: FACTORS[(i / 11) % 11],
        operation: wgpu::BlendOperation::Add,
    };
    let a = wgpu::BlendComponent {
        src_factor: FACTORS[(i / 121) % 11],
        dst_factor: FACTORS[(i / 1331) % 11],
        operation: wgpu::BlendOperation::Add,
    };
    wgpu::BlendState { color: c, alpha: a }
}

struct Ctx {
    device: wgpu::Device,
    queue: wgpu::Queue,
    layout: wgpu::PipelineLayout,
    vbg: wgpu::BindGroupLayout,
}

fn femtovg_source(salt: bool) -> String {
    let shader = include_str!("shader.wgsl");
    let filters = include_str!("filters.wgsl");
    let mut s = format!("{shader}\n{filters}");
    if salt {
        let head = "@fragment\nfn fs_main(vertex: VertexOutput) -> @location(0) vec4<f32> {";
        assert!(s.contains(head), "fs_main header not found in shader.wgsl");
        s = s.replace(head, "fn fs_main_inner(vertex: VertexOutput) -> vec4<f32> {");
        s.push_str("\noverride SALT: f32 = 1.0;\n@fragment\nfn fs_main(v: VertexOutput) -> @location(0) vec4<f32> { return fs_main_inner(v) * SALT; }\n");
    }
    s
}

const TRIVIAL: &str = "
@group(0) @binding(0) var<uniform> viewSize: vec4<f32>;
struct VertexOutput { @builtin(position) position: vec4<f32>, @location(0) t: vec2<f32> };
override SALT: f32 = 1.0;
@vertex fn vs_main(@location(0) v: vec2<f32>, @location(1) t: vec2<f32>) -> VertexOutput {
    var r: VertexOutput; r.position = vec4<f32>(v / viewSize.xy, 0.0, 1.0); r.t = t; return r;
}
@fragment fn fs_main(v: VertexOutput) -> @location(0) vec4<f32> { return vec4<f32>(v.t, 0.0, 1.0) * SALT; }
";

fn make_pipeline(
    ctx: &Ctx,
    module: &wgpu::ShaderModule,
    layout: &wgpu::PipelineLayout,
    blend_index: usize,
    salt: f64,
    stencil: bool,
    vs: &str,
) -> wgpu::RenderPipeline {
    let constants = [("SALT", salt)];
    let fs_opts = wgpu::PipelineCompilationOptions {
        constants: &constants,
        ..Default::default()
    };
    ctx.device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
        label: None,
        layout: Some(layout),
        vertex: wgpu::VertexState {
            module,
            entry_point: Some(vs),
            buffers: &[Some(wgpu::VertexBufferLayout {
                array_stride: 16,
                step_mode: wgpu::VertexStepMode::Vertex,
                attributes: &wgpu::vertex_attr_array![0 => Float32x2, 1 => Float32x2],
            })],
            compilation_options: Default::default(),
        },
        fragment: Some(wgpu::FragmentState {
            module,
            entry_point: Some("fs_main"),
            compilation_options: fs_opts,
            targets: &[Some(wgpu::ColorTargetState {
                format: wgpu::TextureFormat::Bgra8Unorm,
                blend: Some(blend(blend_index)),
                write_mask: wgpu::ColorWrites::ALL,
            })],
        }),
        primitive: wgpu::PrimitiveState {
            topology: wgpu::PrimitiveTopology::TriangleList,
            cull_mode: Some(wgpu::Face::Back),
            ..Default::default()
        },
        depth_stencil: stencil.then(|| wgpu::DepthStencilState {
            format: wgpu::TextureFormat::Stencil8,
            depth_write_enabled: Some(false),
            depth_compare: Some(wgpu::CompareFunction::Always),
            stencil: wgpu::StencilState {
                front: wgpu::StencilFaceState::IGNORE,
                back: wgpu::StencilFaceState::IGNORE,
                read_mask: !0,
                write_mask: !0,
            },
            bias: Default::default(),
        }),
        multisample: Default::default(),
        multiview_mask: None,
        cache: None,
    })
}

fn ms(d: Duration) -> f64 {
    d.as_secs_f64() * 1000.0
}

fn stats(label: &str, v: &[f64]) {
    let mut s = v.to_vec();
    s.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let sum: f64 = s.iter().sum();
    println!(
        "{label:<58} n={:<3} mean={:.3} ms  median={:.3}  min={:.3}  max={:.3}  total={:.1}",
        s.len(),
        sum / s.len() as f64,
        s[s.len() / 2],
        s[0],
        s[s.len() - 1],
        sum
    );
}

fn time_batch(ctx: &Ctx, module: &wgpu::ShaderModule, layout: &wgpu::PipelineLayout, range: std::ops::Range<usize>, salt: f64, vs: &str) -> (Vec<f64>, Vec<wgpu::RenderPipeline>) {
    let mut t = Vec::new();
    let mut keep = Vec::new();
    for i in range {
        let start = Instant::now();
        let p = make_pipeline(ctx, module, layout, i, salt, true, vs);
        t.push(ms(start.elapsed()));
        keep.push(p);
    }
    (t, keep)
}

fn main() {
    let instance = wgpu::Instance::new(wgpu::InstanceDescriptor::new_without_display_handle());
    let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions::default())).unwrap();
    println!("adapter: {:?}", adapter.get_info());
    let (device, queue) = pollster::block_on(adapter.request_device(&wgpu::DeviceDescriptor::default())).unwrap();

    let vbg = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
        label: None,
        entries: &[wgpu::BindGroupLayoutEntry {
            binding: 0,
            visibility: wgpu::ShaderStages::VERTEX,
            ty: wgpu::BindingType::Buffer { ty: wgpu::BufferBindingType::Uniform, has_dynamic_offset: false, min_binding_size: None },
            count: None,
        }],
    });
    let tex = |b| wgpu::BindGroupLayoutEntry {
        binding: b,
        visibility: wgpu::ShaderStages::FRAGMENT,
        ty: wgpu::BindingType::Texture { sample_type: wgpu::TextureSampleType::Float { filterable: true }, view_dimension: wgpu::TextureViewDimension::D2, multisampled: false },
        count: None,
    };
    let samp = |b| wgpu::BindGroupLayoutEntry { binding: b, visibility: wgpu::ShaderStages::FRAGMENT, ty: wgpu::BindingType::Sampler(wgpu::SamplerBindingType::Filtering), count: None };
    let bgl = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
        label: None,
        entries: &[
            wgpu::BindGroupLayoutEntry {
                binding: 0,
                visibility: wgpu::ShaderStages::FRAGMENT,
                ty: wgpu::BindingType::Buffer { ty: wgpu::BufferBindingType::Uniform, has_dynamic_offset: true, min_binding_size: None },
                count: None,
            },
            tex(1),
            samp(2),
            tex(3),
            samp(4),
        ],
    });
    let layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
        label: None,
        bind_group_layouts: &[Some(&vbg), Some(&bgl)],
        immediate_size: 0,
    });
    let trivial_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
        label: None,
        bind_group_layouts: &[Some(&vbg)],
        immediate_size: 0,
    });
    let ctx = Ctx { device, queue, layout, vbg };

    let salt_base = (std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos() % 1_000_000) as f64 * 1e-9;
    let salt = move |k: u32| 1.0 + salt_base + k as f64 * 1e-3;

    let t = Instant::now();
    let femto = ctx.device.create_shader_module(wgpu::ShaderModuleDescriptor { label: None, source: wgpu::ShaderSource::Wgsl(femtovg_source(true).into()) });
    println!("create_shader_module (femtovg shader, salted): {:.3} ms", ms(t.elapsed()));
    let trivial = ctx.device.create_shader_module(wgpu::ShaderModuleDescriptor { label: None, source: wgpu::ShaderSource::Wgsl(TRIVIAL.into()) });

    // 1. A new fragment source (fresh salt) and 20 blend states on it.
    let (a, keep_a) = time_batch(&ctx, &femto, &ctx.layout, 0..1, salt(1), "vs_main");
    stats("femtovg: first pipeline, new MSL source", &a);
    let (b, _keep_b) = time_batch(&ctx, &femto, &ctx.layout, 1..41, salt(1), "vs_main");
    stats("femtovg: 40 more blend states, same MSL source", &b);
    // 2. Recreate the same 40 after they were dropped.
    drop(_keep_b);
    let (c, keep_c) = time_batch(&ctx, &femto, &ctx.layout, 1..41, salt(1), "vs_main");
    stats("femtovg: the same 40 recreated after drop", &c);
    // 3. Same blend states, a different salt: new MSL source each time is NOT the case here;
    //    a new salt means a new MSL source for the first pipeline only.
    let (d, _keep_d) = time_batch(&ctx, &femto, &ctx.layout, 1..41, salt(2), "vs_main_texture");
    stats("femtovg: 40 blend states, new salt + vs_main_texture", &d);
    // 4. Trivial shader for comparison.
    let (e, _keep_e) = time_batch(&ctx, &trivial, &trivial_layout, 0..41, salt(3), "vs_main");
    stats("trivial shader: 41 blend states", &e);

    // 5. Serial vs 4 threads, 40 new pipelines each way.
    let ctx = Arc::new(ctx);
    let femto = Arc::new(femto);
    let t = Instant::now();
    let (_s, _keep_s) = time_batch(&ctx, &femto, &ctx.layout, 41..81, salt(4), "vs_main");
    let serial = ms(t.elapsed());
    let t = Instant::now();
    let handles: Vec<_> = (0..4)
        .map(|k| {
            let ctx = ctx.clone();
            let femto = femto.clone();
            std::thread::spawn(move || {
                let r = 81 + k * 10..81 + (k + 1) * 10;
                time_batch(&ctx, &femto, &ctx.layout, r, salt(4), "vs_main").1.len()
            })
        })
        .collect();
    let n: usize = handles.into_iter().map(|h| h.join().unwrap()).sum();
    println!("serial 40 pipelines: {serial:.1} ms; 4 threads x 10 ({n} pipelines): {:.1} ms wall", ms(t.elapsed()));

    // 6. Does background compilation stall render-thread work (encode + submit + poll)?
    let target = ctx.device.create_texture(&wgpu::TextureDescriptor {
        label: None,
        size: wgpu::Extent3d { width: 256, height: 256, depth_or_array_layers: 1 },
        mip_level_count: 1,
        sample_count: 1,
        dimension: wgpu::TextureDimension::D2,
        format: wgpu::TextureFormat::Bgra8Unorm,
        usage: wgpu::TextureUsages::RENDER_ATTACHMENT,
        view_formats: &[],
    });
    let stencil = ctx.device.create_texture(&wgpu::TextureDescriptor {
        format: wgpu::TextureFormat::Stencil8,
        ..target.__descriptor_like()
    });
    let view = target.create_view(&Default::default());
    let sview = stencil.create_view(&Default::default());
    let ubuf = ctx.device.create_buffer(&wgpu::BufferDescriptor { label: None, size: 256, usage: wgpu::BufferUsages::UNIFORM, mapped_at_creation: false });
    let vbuf = ctx.device.create_buffer(&wgpu::BufferDescriptor { label: None, size: 4096, usage: wgpu::BufferUsages::VERTEX, mapped_at_creation: false });
    let bg0 = ctx.device.create_bind_group(&wgpu::BindGroupDescriptor { label: None, layout: &ctx.vbg, entries: &[wgpu::BindGroupEntry { binding: 0, resource: ubuf.as_entire_binding() }] });
    let triv_pipe = make_pipeline(&ctx, &trivial, &trivial_layout, 7, salt(3), true, "vs_main");
    let frame = |ctx: &Ctx| {
        let mut enc = ctx.device.create_command_encoder(&Default::default());
        {
            let mut rp = enc.begin_render_pass(&wgpu::RenderPassDescriptor {
                label: None,
                color_attachments: &[Some(wgpu::RenderPassColorAttachment { view: &view, depth_slice: None, resolve_target: None, ops: wgpu::Operations { load: wgpu::LoadOp::Clear(wgpu::Color::BLACK), store: wgpu::StoreOp::Store } })],
                depth_stencil_attachment: Some(wgpu::RenderPassDepthStencilAttachment { view: &sview, depth_ops: None, stencil_ops: Some(wgpu::Operations { load: wgpu::LoadOp::Clear(0), store: wgpu::StoreOp::Store }) }),
                timestamp_writes: None,
                occlusion_query_set: None,
                multiview_mask: None,
            });
            rp.set_pipeline(&triv_pipe);
            rp.set_bind_group(0, &bg0, &[]);
            rp.set_vertex_buffer(0, vbuf.slice(..));
            for _ in 0..200 {
                rp.draw(0..6, 0..1);
            }
        }
        ctx.queue.submit([enc.finish()]);
        ctx.device.poll(wgpu::PollType::wait_indefinitely()).unwrap();
    };
    let mut base = Vec::new();
    for _ in 0..200 {
        let t = Instant::now();
        frame(&ctx);
        base.push(ms(t.elapsed()));
    }
    stats("render-thread frame, no background compile", &base);
    let bg = {
        let ctx = ctx.clone();
        let femto = femto.clone();
        std::thread::spawn(move || {
            let t = Instant::now();
            let r = time_batch(&ctx, &femto, &ctx.layout, 200..280, salt(5), "vs_main");
            (ms(t.elapsed()), r.1.len())
        })
    };
    let mut during = Vec::new();
    while !bg.is_finished() {
        let t = Instant::now();
        frame(&ctx);
        during.push(ms(t.elapsed()));
    }
    let (bg_ms, bg_n) = bg.join().unwrap();
    stats("render-thread frame, while a thread compiles 80 pipelines", &during);
    println!("background thread: {bg_n} pipelines in {bg_ms:.1} ms");
    drop((keep_a, keep_c));
}

trait DescLike {
    fn __descriptor_like(&self) -> wgpu::TextureDescriptor<'static>;
}
impl DescLike for wgpu::Texture {
    fn __descriptor_like(&self) -> wgpu::TextureDescriptor<'static> {
        wgpu::TextureDescriptor {
            label: None,
            size: self.size(),
            mip_level_count: 1,
            sample_count: 1,
            dimension: wgpu::TextureDimension::D2,
            format: self.format(),
            usage: self.usage(),
            view_formats: &[],
        }
    }
}
