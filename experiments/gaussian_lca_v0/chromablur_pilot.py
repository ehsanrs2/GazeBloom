#!/usr/bin/env python3
"""A parameterized, illustrative Gaussian/LCA model; NOT a validated ChromaBlur reproduction.

Dependencies: numpy, scipy (optional), opencv-python, Pillow.

This model uses an equivalent Gaussian blur diameter for geometric defocus
and variance subtraction against the viewer's assumed chromatic baseline.
It does not use the original authors' wave-optics PSF and search algorithm.
The generated media are display stimuli, not a treatment or a measure of actual
accommodation. All physical parameters are illustrative assumptions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

WAVELENGTH_NM = {"R": 617.0, "G": 520.0, "B": 449.0}


def lca_diopters(wavelength_nm: float) -> float:
    # Cholewiak, Love, Banks 2018, eq. 3 (D=0 at 520 nm).
    return 2.071 - 633.46 / (wavelength_nm - 214.10)


def blur_sigma_px(delta_d: float, lambda_nm: float,
                  screen_distance_m: float, pixel_pitch_mm: float,
                  pupil_mm: float) -> float:
    """Illustrative per-channel display sigma, after baseline PSF compensation.

    Defocus circle angular diameter (rad) ~= pupil_m * |defocus_D|.
    Gaussian approximation std=0.55*(circle diameter/2), following the
    Gaussian/cylinder matching convention discussed in the paper.
    Display blur variance >= 0, so it cannot 'undo' ocular blur.
    """
    rad_per_px = (pixel_pitch_mm / 1000.0) / screen_distance_m
    sigma_per_diopter = 0.275 * (pupil_mm / 1000.0) / rad_per_px
    lca = lca_diopters(lambda_nm)
    return float(sigma_per_diopter * math.sqrt(max(0.0, (delta_d + lca)**2 - lca**2)))


def linearize_srgb(im: np.ndarray) -> np.ndarray:
    return np.where(im <= 0.04045, im / 12.92, ((im + 0.055) / 1.055)**2.4)


def encode_srgb(im: np.ndarray) -> np.ndarray:
    return np.where(im <= 0.0031308, im * 12.92, 1.055 * np.power(np.maximum(im, 0), 1/2.4) - 0.055)


def make_texture(w: int, h: int, seed: int = 314159) -> np.ndarray:
    """Deterministic 1/f Fourier-amplitude texture + optotype/ring/edge detail."""
    rng = np.random.default_rng(seed)
    white = rng.normal(0, 1, (h, w)).astype(np.float32)
    freq_y = np.fft.fftfreq(h)[:, None]
    freq_x = np.fft.fftfreq(w)[None, :]
    rad = np.sqrt(freq_x**2 + freq_y**2)
    filt = 1 / np.maximum(rad, 1 / max(w, h))
    filt[0, 0] = 0
    textured = np.fft.ifft2(np.fft.fft2(white) * filt).real
    textured = (textured - textured.mean()) / (textured.std() + 1e-6)
    a = np.clip(0.5 + textured * 0.16, 0.10, 0.90)
    rgb8 = np.uint8(np.round(a * 255))
    # Add visual landmarks; exactly the same base is used across all conditions.
    cv2.rectangle(rgb8, (int(w*.07), int(h*.15)), (int(w*.36), int(h*.82)), 243, -1)
    cv2.rectangle(rgb8, (int(w*.07), int(h*.15)), (int(w*.36), int(h*.82)), 20, 3)
    for i in range(12):
        y = int(h*(0.20 + 0.052 * i))
        cv2.line(rgb8, (int(w*.10), y), (int(w*.32), y), 20 if i%2 else 50, 1 + (i%3))
    center=(int(w*.70), int(h*.50))
    for r in [17, 32, 49, 68, 88, 107, 126]:
        if r < h*.45:
            cv2.circle(rgb8,center,r, 248 if r%2 else 10,3)
    cv2.line(rgb8,(center[0]-10,center[1]),(center[0]+10,center[1]), 20,2)
    cv2.line(rgb8,(center[0],center[1]-10),(center[0],center[1]+10), 20,2)
    # 3 optotype characters on a flat white field (high-frequency edges).
    cv2.rectangle(rgb8,(int(w*.40), int(h*.77)),(int(w*.95),int(h*.97)), 236, -1)
    cv2.putText(rgb8,'E  F  P  T', (int(w*.43),int(h*.91)),
                cv2.FONT_HERSHEY_SIMPLEX,1.15,20,2,cv2.LINE_AA)
    return (rgb8.astype(np.float32) / 255.0)


def render(base_srgb: np.ndarray, delta_d: float, mode: str,
           dist_m: float, pitch_mm: float, pupil_mm: float) -> np.ndarray:
    base_lin = linearize_srgb(base_srgb.astype(np.float32))
    if mode == 'lca':
        sigmas=[blur_sigma_px(delta_d,WAVELENGTH_NM[c],dist_m,pitch_mm,pupil_mm)
                for c in 'RGB']
    elif mode == 'control':
        # Same magnitude and spatial profile per RGB channel (no directional chromatic cue).
        sigmas=[blur_sigma_px(delta_d,520.0,dist_m,pitch_mm,pupil_mm)]*3
    elif mode == 'reference':
        sigmas=[0,0,0]
    else:
        raise ValueError(mode)
    planes=[]
    for sigma in sigmas:
        if sigma < 1e-5:
            planes.append(base_lin.copy())
        else:
            planes.append(cv2.GaussianBlur(base_lin, (0,0), sigmaX=sigma,
                                           sigmaY=sigma, borderType=cv2.BORDER_REFLECT_101))
    srgb = encode_srgb(np.clip(np.stack(planes,axis=-1),0,1))
    return (np.clip(srgb,0,1)*255+0.5).astype(np.uint8)


def save_rgb(path: Path, image_rgb: np.ndarray):
    Image.fromarray(image_rgb).save(path)


def montage(images: list[tuple[str, Path]], out: Path, target_size=(640,400)):
    cols=2
    width=target_size[0]*cols+60
    rows=math.ceil(len(images)/cols)
    height=(target_size[1]+68)*rows+45
    board=Image.new('RGB',(width,height),(242,244,246))
    draw=ImageDraw.Draw(board)
    for idx,(name,path) in enumerate(images):
        col=idx%cols
        row=idx//cols
        x=20+col*(target_size[0]+20)
        y=16+row*(target_size[1]+68)
        im=Image.open(path).resize(target_size,resample=Image.Resampling.LANCZOS)
        board.paste(im,(x,y+32))
        draw.text((x,y+4),name,fill=(18,30,47))
    board.save(out)


def create_video(base: np.ndarray, out: Path, mode: str,
                 dist_m: float, pitch_mm: float, pupil_mm: float,
                 amplitude_d: float, seconds: float, fps: int):
    h,w=base.shape
    v = cv2.VideoWriter(str(out),cv2.VideoWriter_fourcc(*'mp4v'),fps,(w,h+54))
    if not v.isOpened():
        raise RuntimeError('Video writer failed: '+str(out))
    for k in range(round(seconds*fps)):
        t=k/fps
        delta=amplitude_d*math.sin(2*math.pi*t/seconds)
        img=render(base,delta,mode,dist_m,pitch_mm,pupil_mm)
        canvas=np.full((h+54,w,3),240,np.uint8)
        canvas[:h]=img
        phrase=f'{mode.upper()}  |  simulated delta {delta:+.2f} D  |  t={t:.1f}s'
        cv2.putText(canvas,phrase,(18,h+34),cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,(22,30,46),2,cv2.LINE_AA)
        v.write(cv2.cvtColor(canvas,cv2.COLOR_RGB2BGR))
    v.release()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',type=Path,default=Path('.'))
    p.add_argument('--distance-m',type=float,default=0.60)
    p.add_argument('--pixel-pitch-mm',type=float,default=0.27)
    p.add_argument('--pupil-mm',type=float,default=4.0)
    p.add_argument('--amplitude-d',type=float,default=0.45)
    p.add_argument('--seconds',type=float,default=10.0)
    p.add_argument('--fps',type=int,default=15)
    p.add_argument('--width',type=int,default=768)
    p.add_argument('--height',type=int,default=480)
    args=p.parse_args()
    assert 0.10<=args.distance_m<=5.0
    assert 0.05<=args.pixel_pitch_mm<=1.0
    assert 1.0<=args.pupil_mm<=8.0
    assert 0.05<=args.amplitude_d<=1.0
    assert 4<=args.fps<=60
    assert 256<=args.width<=1920 and 240<=args.height<=1080
    args.out.mkdir(parents=True,exist_ok=True)
    base=make_texture(args.width,args.height)
    cases=[('reference','reference',0.0),
           ('control_near','control', args.amplitude_d),
           ('lca_near','lca',args.amplitude_d),
           ('control_far','control',-args.amplitude_d),
           ('lca_far','lca',-args.amplitude_d)]
    for name,mode,delta in cases:
        save_rgb(args.out/f'{name}.png',render(base,delta,mode,args.distance_m,args.pixel_pitch_mm,args.pupil_mm))
    montage([
        ('A  Sharp reference',args.out/'reference.png'),
        ('B  Defocus-only control  (+D)',args.out/'control_near.png'),
        ('C  LCA-inspired, near cue  (+D)',args.out/'lca_near.png'),
        ('D  LCA-inspired, far cue  (-D)',args.out/'lca_far.png'),
    ],args.out/'comparison.png')
    create_video(base,args.out/'lca_cycle.mp4','lca',args.distance_m,args.pixel_pitch_mm,
                 args.pupil_mm,args.amplitude_d,args.seconds,args.fps)
    create_video(base,args.out/'control_cycle.mp4','control',args.distance_m,args.pixel_pitch_mm,
                 args.pupil_mm,args.amplitude_d,args.seconds,args.fps)
    summary={
        'model':'illustrative gaussian defocus and LCA, NOT reproduction of ChromaBlur study',
        'parameters': {'distance_m':args.distance_m,'pixel_pitch_mm':args.pixel_pitch_mm,
             'pupil_mm':args.pupil_mm,'amplitude_d':args.amplitude_d,
             'video_seconds':args.seconds,'fps':args.fps,
             'image_width':args.width,'image_height':args.height},
        'chromatic_wavelength_nm':WAVELENGTH_NM,
        'lca_diopters':{c:round(lca_diopters(w),4) for c,w in WAVELENGTH_NM.items()},
        'sigma_px':{key:{c:round(blur_sigma_px(d,WAVELENGTH_NM[c],args.distance_m,args.pixel_pitch_mm,args.pupil_mm),3) for c in 'RGB'}
                  for key,d in [('near',args.amplitude_d),('far',-args.amplitude_d)]},
        'expected_direction': 'positive delta means simulated closer stimulus, negative delta farther; actual screen remains fixed',
        'files':{}
    }
    for file in sorted(args.out.iterdir()):
        if file.is_file() and file.name not in ('manifest.json','README_FA.md'):
            summary['files'][file.name]={'size_bytes':file.stat().st_size,'sha256':hashlib.sha256(file.read_bytes()).hexdigest()}
    (args.out/'manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary['sigma_px'],indent=2))
    print('Created:',[f.name for f in sorted(args.out.iterdir())])


if __name__=='__main__':
    main()