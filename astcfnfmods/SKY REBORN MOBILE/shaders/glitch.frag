#pragma header
#extension GL_EXT_gpu_shader4 : enable

uniform float time = 0.0;
uniform float prob = 0.0;
uniform float intensityChromatic = 0.0;
const int sampleCount = 50;

float _round(float n) {
    return floor(n + 0.5);
}

vec2 _round(vec2 n) {
    return floor(n + 0.5);
}

vec3 tex2D(sampler2D _tex,vec2 _p)
{
    vec3 col = flixel_texture2D(_tex,_p).xyz;
    if(.5<abs(_p.x-0.5)){
        col=vec3(0.1);
    }
    return col;
}

#define PI 3.14159265359
#define PHI (1.618033988749895)

float rand(vec2 co){
    return fract(sin(dot(co.xy ,vec2(12.9898,78.233))) * 43758.5453);
}

const float glitchScale = 0.4;

vec2 glitchCoord(vec2 p, vec2 gridSize) {
	vec2 coord = floor(p / gridSize) * gridSize;
    coord += (gridSize / 2.0);
    return coord;
}

struct GlitchSeed {
    vec2 seed;
    float prob;
};
    
float fBox2d(vec2 p, vec2 b) {
  vec2 d = abs(p) - b;
  return min(max(d.x, d.y), 0.0) + length(max(d, 0.0));
}

GlitchSeed glitchSeed(vec2 p, float speed) {
    float seedTime = floor(time * speed);
    vec2 seed = vec2(
        1.0 + mod(seedTime / 100.0, 100.0),
        1.0 + mod(seedTime, 100.0)
    ) / 100.0;
    seed += p; 
    return GlitchSeed(seed, prob);
}

float shouldApply(GlitchSeed seed) {
    return round(
        mix(
            mix(rand(seed.seed), 1.0, seed.prob - 0.5),
            0.0,
            (1.0 - seed.prob) * 0.5
        )
    );
}

const float GAMMA = 1;

vec3 gamma(vec3 color, float g) {
    return pow(color, vec3(g));
}

vec3 linearToScreen(vec3 linearRGB) {
    return gamma(linearRGB, 1.0 / GAMMA);
}

vec4 swapCoords(vec2 seed, vec2 groupSize, vec2 subGrid, vec2 blockSize) {
    vec2 rand2 = vec2(rand(seed), rand(seed+0.1));
    vec2 range = subGrid - (blockSize - 1.0);
    vec2 coord = floor(rand2 * range) / subGrid;
    vec2 bottomLeft = coord * groupSize;
    vec2 realBlockSize = (groupSize / subGrid) * blockSize;
    vec2 topRight = bottomLeft + realBlockSize;
    topRight -= groupSize / 2.0;
    bottomLeft -= groupSize / 2.0;
    return vec4(bottomLeft, topRight);
}

float isInBlock(vec2 pos, vec4 block) {
    vec2 a = sign(pos - block.xy);
    vec2 b = sign(block.zw - pos);
    return min(sign(a.x + a.y + b.x + b.y - 3.0), 0.0);
}

vec2 moveDiff(vec2 pos, vec4 swapA, vec4 swapB) {
    vec2 diff = swapB.xy - swapA.xy;
    return diff * isInBlock(pos, swapA);
}

void swapBlocks(inout vec2 xy, vec2 groupSize, vec2 subGrid, vec2 blockSize, vec2 seed, float apply) {
    
    vec2 groupOffset = glitchCoord(xy, groupSize);
    vec2 pos = xy - groupOffset;
    
    vec2 seedA = seed * groupOffset;
    vec2 seedB = seed * (groupOffset + 0.1);
    
    vec4 swapA = swapCoords(seedA, groupSize, subGrid, blockSize);
    vec4 swapB = swapCoords(seedB, groupSize, subGrid, blockSize);
    
    vec2 newPos = pos;
    newPos += moveDiff(pos, swapA, swapB) * apply;
    newPos += moveDiff(pos, swapB, swapA) * apply;
    pos = newPos;
    
    xy = pos + groupOffset;
}



void staticNoise(inout vec2 p, vec2 groupSize, float grainSize, float contrast) {
    GlitchSeed seedA = glitchSeed(glitchCoord(p, groupSize), 5.0);
    seedA.prob *= 0.5;
    if (shouldApply(seedA) == 1.0) {
        GlitchSeed seedB = glitchSeed(glitchCoord(p, vec2(grainSize)), 5.0);
        vec2 offset = vec2(rand(seedB.seed), rand(seedB.seed + 0.1));
        offset = round(offset * 2.0 - 1.0);
        offset *= contrast;
        p += offset;
    }
}


void freezeTime(vec2 p, inout float time, vec2 groupSize, float speed) {
    GlitchSeed seed = glitchSeed(glitchCoord(p, groupSize), speed);
    if (shouldApply(seed) == 1.0) {
        float frozenTime = floor(time * speed) / speed;
        time = frozenTime;
    }
}


void glitchSwap(inout vec2 p) {

    vec2 pp = p;
    
    float scale = glitchScale;
    float speed = 5.0;
    
    vec2 groupSize;
    vec2 subGrid;
    vec2 blockSize;    
    GlitchSeed seed;
    float apply;
    
    groupSize = vec2(0.6) * scale;
    subGrid = vec2(2);
    blockSize = vec2(1);

    seed = glitchSeed(glitchCoord(p, groupSize), speed);
    apply = shouldApply(seed);
    swapBlocks(p, groupSize, subGrid, blockSize, seed.seed, apply);
    
    groupSize = vec2(0.8) * scale;
    subGrid = vec2(3);
    blockSize = vec2(1);
    
    seed = glitchSeed(glitchCoord(p, groupSize), speed);
    apply = shouldApply(seed);
    swapBlocks(p, groupSize, subGrid, blockSize, seed.seed, apply);

    groupSize = vec2(0.2) * scale;
    subGrid = vec2(6);
    blockSize = vec2(1);
    
    seed = glitchSeed(glitchCoord(p, groupSize), speed);
    float apply2 = shouldApply(seed);
    swapBlocks(p, groupSize, subGrid, blockSize, (seed.seed + 1.), apply * apply2);
    swapBlocks(p, groupSize, subGrid, blockSize, (seed.seed + 2.), apply * apply2);
    swapBlocks(p, groupSize, subGrid, blockSize, (seed.seed + 3.), apply * apply2);
    swapBlocks(p, groupSize, subGrid, blockSize, (seed.seed + 4.), apply * apply2);
    swapBlocks(p, groupSize, subGrid, blockSize, (seed.seed + 5.), apply * apply2);
    
    groupSize = vec2(1.2, 0.2) * scale;
    subGrid = vec2(9,2);
    blockSize = vec2(3,1);
    
    seed = glitchSeed(glitchCoord(p, groupSize), speed);
    apply = shouldApply(seed);
    swapBlocks(p, groupSize, subGrid, blockSize, seed.seed, apply);
}

void glitchStatic(inout vec2 p) {
    staticNoise(p, vec2(0.5, 0.25/2.0) * glitchScale, 0.2 * glitchScale, 2.0);
}

void glitchTime(vec2 p, inout float time) {
   freezeTime(p, time, vec2(0.5) * glitchScale, 2.0);
}

void glitchColor(vec2 p, inout vec3 color) {
    vec2 groupSize = vec2(0.75,0.125) * glitchScale;
    vec2 subGrid = vec2(0,6);
    float speed = 5.0;
    GlitchSeed seed = glitchSeed(glitchCoord(p, groupSize), speed);
    seed.prob *= 0.3;
    if (shouldApply(seed) == 1.0) 
        color = vec3(0, 0, 0);
}

vec4 transverseChromatic(vec2 p) {
    vec2 destCoord = p;
    vec2 direction = normalize(destCoord - 0.5); 
    vec2 velocity = direction * intensityChromatic * pow(length(destCoord - 0.5), 3.0);
	float inverseSampleCount = 1.0 / float(sampleCount); 
    
    mat3x2 increments = mat3x2(velocity * 1.0 * inverseSampleCount, velocity * 2.0 * inverseSampleCount, velocity * 4.0 * inverseSampleCount);

    vec3 accumulator = vec3(0);
    mat3x2 offsets = mat3x2(0); 
    for (int i = 0; i < sampleCount; i++) {
        accumulator.r += flixel_texture2D(bitmap, destCoord + offsets[0]).r; 
        accumulator.g += flixel_texture2D(bitmap, destCoord + offsets[1]).g; 
        accumulator.b += flixel_texture2D(bitmap, destCoord + offsets[2]).b;         
        offsets -= increments;
    }
    vec4 newColor = vec4(accumulator / float(sampleCount), 1.0);
	return newColor;
}

void main() {
    float alpha = openfl_Alphav;
    vec2 p = openfl_TextureCoordv.xy;
    vec4 color = flixel_texture2D(bitmap, p);
    
    glitchSwap(p);
    glitchStatic(p);

    color.rgb = transverseChromatic(p).rgb;
    glitchColor(p, color.rgb);

    gl_FragColor = vec4(color);
}