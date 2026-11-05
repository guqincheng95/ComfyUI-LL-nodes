// Display-referred sRGB preview of modules/photo/processing.py.
// The final full-resolution output continues to use the Python implementation.
const vertex = `#version 300 es
void main() {
  vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}`;

const fragment = `#version 300 es
precision highp float;
precision highp int;
uniform highp usampler2D pixels;
uniform bool bypass, preserve;
uniform float ev, contrast, highlights, shadows, whites, blacks, temperature, tint, vibrance, saturation;
uniform vec3 shadow, midtone, highlight;
out vec4 color;
const vec3 W = vec3(.2126,.7152,.0722);
float Y(vec3 rgb) { return dot(rgb,W); }
float lo(vec3 v) { return min(min(v.x,v.y),v.z); }
float hi(vec3 v) { return max(max(v.x,v.y),v.z); }
vec3 linearize(vec3 v) {
  return mix(pow(max((v+.055)/1.055,0.),vec3(2.4)),v/12.92,lessThanEqual(v,vec3(.04045)));
}
vec3 encode(vec3 v) {
  return mix(1.055*pow(max(v,0.),vec3(1./2.4))-.055,v*12.92,lessThanEqual(v,vec3(.0031308)));
}
float encode(float v) { return encode(vec3(v)).x; }
vec3 gamut(vec3 rgb,float target) {
  target=clamp(target,0.,1.);
  vec3 c=rgb-Y(rgb);
  vec3 upper=(1.-target)/max(c,1e-8), lower=target/max(-c,1e-8);
  vec3 limits=mix(mix(vec3(1.),lower,lessThan(c,vec3(0.))),upper,greaterThan(c,vec3(0.)));
  return clamp(target+clamp(lo(limits),0.,1.)*c,0.,1.);
}
float curve(float x) {
  if(contrast!=0.) {
    float power=exp2(contrast), a=pow(x,power), b=pow(1.-x,power);
    x=a/max(a+b,1e-8);
  }
  if(shadows!=0.) { float u=clamp(x/.55,0.,1.); x+=.55*.9*shadows*u*(1.-u)*(1.-u); }
  if(highlights!=0.) { float u=clamp((x-.45)/.55,0.,1.); x+=.55*.9*highlights*u*u*(1.-u); }
  if(blacks!=0.) x+=.12*blacks*(1.-smoothstep(0.,.25,x));
  if(whites!=0.) x+=.12*whites*smoothstep(.75,1.,x);
  return clamp(x,0.,1.);
}
void main() {
  ivec2 xy=ivec2(gl_FragCoord.xy);
  xy.y=textureSize(pixels,0).y-1-xy.y;
  vec4 base=vec4(texelFetch(pixels,xy,0))/65535.;
  if(bypass) { color=base; return; }
  vec3 rgb=linearize(base.rgb);
  if(temperature!=0. || tint!=0.) {
    vec3 gain=exp2(vec3(.7*temperature+.35*tint,-.35*tint,-.7*temperature+.35*tint));
    rgb*=gain/Y(gain);
  }
  rgb*=exp2(ev);
  float y=Y(rgb);
  if(contrast!=0. || highlights!=0. || shadows!=0. || whites!=0. || blacks!=0.) {
    float target=linearize(vec3(curve(clamp(encode(y),0.,1.)))).x;
    rgb=gamut(y>1e-8 ? rgb*(target/y) : vec3(target),target);
  } else rgb=gamut(rgb,y);
  if(any(notEqual(shadow,vec3(0.))) || any(notEqual(midtone,vec3(0.))) || any(notEqual(highlight,vec3(0.)))) {
    y=Y(rgb); float l=encode(y), s=1.-smoothstep(.15,.55,l), h=smoothstep(.45,.85,l);
    vec3 candidate=rgb+(s*shadow+(1.-s-h)*midtone+h*highlight)*.35*sqrt(max(y*(1.-y),0.));
    rgb=preserve ? gamut(candidate,y) : clamp(candidate,0.,1.);
  }
  if(vibrance!=0. || saturation!=0.) {
    y=Y(rgb);
    float sat=(hi(rgb)-lo(rgb))/max(hi(rgb),1e-8);
    float factor=(vibrance>=0. ? 1.+vibrance*(1.-sat)*(1.-sat) : 1.+vibrance)*(1.+saturation);
    rgb=gamut(y+(rgb-y)*factor,y);
  }
  color=vec4(clamp(encode(rgb),0.,1.),base.a);
}`;

const scalarNames = ['contrast','highlights','shadows','whites','blacks','temperature','tint','vibrance','saturation'];
const regions = ['shadow','midtone','highlight'];
const axes = ['cyan_red','magenta_green','yellow_blue'];

export function createPhotoRenderer(canvas, options={}) {
  const gl=canvas.getContext('webgl2',{alpha:true,premultipliedAlpha:false,antialias:false,...options});
  if(!gl)throw Error('WebGL2 不可用');
  const program=gl.createProgram();
  const shaders=[];
  try {
    for(const [kind,source] of [[gl.VERTEX_SHADER,vertex],[gl.FRAGMENT_SHADER,fragment]]) {
      const shader=gl.createShader(kind); shaders.push(shader);
      gl.shaderSource(shader,source);gl.compileShader(shader);
      if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(shader));
      gl.attachShader(program,shader);
    }
    gl.linkProgram(program);
    if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(program));
  } catch(error) {
    gl.deleteProgram(program);throw error;
  } finally {
    for(const shader of shaders)gl.deleteShader(shader);
  }
  const texture=gl.createTexture(), vao=gl.createVertexArray();
  gl.useProgram(program);
  const uniform=Object.fromEntries(['pixels','ev','bypass','preserve',...scalarNames,...regions]
    .map(key=>[key,gl.getUniformLocation(program,key)]));
  gl.uniform1i(uniform.pixels,0);
  gl.bindVertexArray(vao);
  gl.bindTexture(gl.TEXTURE_2D,texture);
  gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.NEAREST);
  const value=(p,key)=>Number(p[key])||0;
  return {
    upload(width,height,pixels) {
      canvas.width=width;canvas.height=height;gl.viewport(0,0,width,height);
      gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA16UI,width,height,0,gl.RGBA_INTEGER,gl.UNSIGNED_SHORT,pixels);
      if(gl.getError()!==gl.NO_ERROR)throw Error('预览图载入失败');
    },
    draw(p={},compare=false) {
      const ev=value(p,'exposure');
      const vectors=regions.map(region=>axes.map(axis=>value(p,region+'_'+axis)/100));
      gl.uniform1i(uniform.bypass,Number(compare||(!ev&&!scalarNames.some(key=>value(p,key))&&!vectors.flat().some(Boolean))));
      gl.uniform1i(uniform.preserve,Number(p.preserve_luminosity!==false));
      gl.uniform1f(uniform.ev,ev);
      for(const key of scalarNames)gl.uniform1f(uniform[key],value(p,key)/100);
      for(let i=0;i<regions.length;i++)gl.uniform3f(uniform[regions[i]],...vectors[i]);
      gl.drawArrays(gl.TRIANGLES,0,3);
    },
    dispose(){gl.deleteTexture(texture);gl.deleteVertexArray(vao);gl.deleteProgram(program);}
  };
}
