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
    if std::env::var("STUB_FILTERS").is_ok() {
        for f in ["renderFilteredImage", "renderColorMatrix", "renderTurbulence", "renderTransfer", "renderBlend", "renderMorphology", "renderOffset"] {
            s = s.replace(&format!("return {f}(vertex, params);"), "return vec4<f32>(0.0);");
        }
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

#[derive(Clone, Copy)]
struct Variant {
    blend: Option<usize>,
    write_all: bool,
    stencil_op: wgpu::StencilOperation,
    compare: wgpu::CompareFunction,
    write_mask: u32,
    topology: wgpu::PrimitiveTopology,
    cull: Option<wgpu::Face>,
}

const BASE: Variant = Variant {
    blend: Some(7 * 11 + 1),
    write_all: true,
    stencil_op: wgpu::StencilOperation::Keep,
    compare: wgpu::CompareFunction::Always,
    write_mask: 0xff,
    topology: wgpu::PrimitiveTopology::TriangleList,
    cull: Some(wgpu::Face::Back),
};

fn make(device: &wgpu::Device, module: &wgpu::ShaderModule, layout: &wgpu::PipelineLayout, v: Variant, salt: f64) -> wgpu::RenderPipeline {
    let constants = [("SALT", salt)];
    let face = wgpu::StencilFaceState { compare: v.compare, fail_op: v.stencil_op, depth_fail_op: v.stencil_op, pass_op: v.stencil_op };
    device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
        label: None,
        layout: Some(layout),
        vertex: wgpu::VertexState {
            module,
            entry_point: Some("vs_main"),
            buffers: &[Some(wgpu::VertexBufferLayout { array_stride: 16, step_mode: wgpu::VertexStepMode::Vertex, attributes: &wgpu::vertex_attr_array![0 => Float32x2, 1 => Float32x2] })],
            compilation_options: Default::default(),
        },
        fragment: Some(wgpu::FragmentState {
            module,
            entry_point: Some("fs_main"),
            compilation_options: wgpu::PipelineCompilationOptions { constants: &constants, ..Default::default() },
            targets: &[Some(wgpu::ColorTargetState {
                format: wgpu::TextureFormat::Bgra8Unorm,
                blend: v.blend.map(blend),
                write_mask: if v.write_all { wgpu::ColorWrites::ALL } else { wgpu::ColorWrites::empty() },
            })],
        }),
        primitive: wgpu::PrimitiveState { topology: v.topology, cull_mode: v.cull, ..Default::default() },
        depth_stencil: Some(wgpu::DepthStencilState {
            format: wgpu::TextureFormat::Stencil8,
            depth_write_enabled: Some(false),
            depth_compare: Some(wgpu::CompareFunction::Always),
            stencil: wgpu::StencilState { front: face, back: face, read_mask: 0xff, write_mask: v.write_mask },
            bias: Default::default(),
        }),
        multisample: Default::default(),
        multiview_mask: None,
        cache: None,
    })
}

fn main() {
    let instance = wgpu::Instance::new(wgpu::InstanceDescriptor::new_without_display_handle());
    let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions::default())).unwrap();
    let (device, _queue) = pollster::block_on(adapter.request_device(&wgpu::DeviceDescriptor::default())).unwrap();
    let ubo = |vis, dynamic| wgpu::BindGroupLayoutEntry { binding: 0, visibility: vis, ty: wgpu::BindingType::Buffer { ty: wgpu::BufferBindingType::Uniform, has_dynamic_offset: dynamic, min_binding_size: None }, count: None };
    let tex = |b| wgpu::BindGroupLayoutEntry { binding: b, visibility: wgpu::ShaderStages::FRAGMENT, ty: wgpu::BindingType::Texture { sample_type: wgpu::TextureSampleType::Float { filterable: true }, view_dimension: wgpu::TextureViewDimension::D2, multisampled: false }, count: None };
    let samp = |b| wgpu::BindGroupLayoutEntry { binding: b, visibility: wgpu::ShaderStages::FRAGMENT, ty: wgpu::BindingType::Sampler(wgpu::SamplerBindingType::Filtering), count: None };
    let vbg = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor { label: None, entries: &[ubo(wgpu::ShaderStages::VERTEX, false)] });
    let bgl = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor { label: None, entries: &[ubo(wgpu::ShaderStages::FRAGMENT, true), tex(1), samp(2), tex(3), samp(4)] });
    let layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor { label: None, bind_group_layouts: &[Some(&vbg), Some(&bgl)], immediate_size: 0 });
    let module = device.create_shader_module(wgpu::ShaderModuleDescriptor { label: None, source: wgpu::ShaderSource::Wgsl(femtovg_source(true).into()) });

    // FIXED_SALT=x reuses one fragment source across processes (warm Metal disk cache).
    let salt: f64 = std::env::var("FIXED_SALT").ok().and_then(|s| s.parse().ok()).unwrap_or_else(|| {
        1.0 + (std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos() % 1_000_000) as f64 * 1e-9
    });

    let mut keep = Vec::new();
    let mut run = |label: &str, v: Variant| {
        let t = std::time::Instant::now();
        keep.push(make(&device, &module, &layout, v, salt));
        println!("{label:<60} {:>8.3} ms", t.elapsed().as_secs_f64() * 1000.0);
    };
    use wgpu::{CompareFunction as C, StencilOperation as O};
    run("base (SourceOver-like blend), new source", BASE);
    run("same as base again (wgpu does not dedupe)", BASE);
    run("stencil ops IncrementClamp", Variant { stencil_op: O::IncrementClamp, ..BASE });
    run("stencil compare Equal", Variant { compare: C::Equal, ..BASE });
    run("stencil write_mask 0x7f", Variant { write_mask: 0x7f, ..BASE });
    run("topology TriangleStrip", Variant { topology: wgpu::PrimitiveTopology::TriangleStrip, ..BASE });
    run("cull None", Variant { cull: None, ..BASE });
    run("blend None, color writes empty (stencil-only pass)", Variant { blend: None, write_all: false, ..BASE });
    run("blend None, color writes empty, stencil IncrementWrap", Variant { blend: None, write_all: false, stencil_op: O::IncrementWrap, ..BASE });
    run("different blend state", Variant { blend: Some(1 * 11 + 7), ..BASE });
    run("another blend state", Variant { blend: Some(1 * 11 + 0), ..BASE });
    run("blend None, write ALL", Variant { blend: None, ..BASE });
}
