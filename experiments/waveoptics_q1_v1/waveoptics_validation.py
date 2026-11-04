#!/usr/bin/env python3
"""Reproducible first-pass Q1 test for a wave-optics + LCA visual stimulus.

Not a replication of the 2018 Cholewiak et al. rendering code.
Not a validated eye model or medical/vision-therapy stimulus.

Uses a circular pupil, scalar monochromatic Fraunhofer diffraction,
quadratic wavefront defocus, simple empirical LCA, wavelength-independent
pupil transmittance, sampled RGB primary peak wavelengths, and projected
screen-pixel integration. Finds NONNEGATIVE isotropic Gaussian display blur
sigmas that minimize the discrepancy between target retinal PSFs and
predicted retinal PSFs when viewed at the FIXED monitor distance.

Key distinction: a Gaussian display kernel cannot sharpen the baseline
optical PSF. Therefore some desired chromatic defocus conditions may be
unreproducible with this restricted family of nonnegative display blurs.

Dependencies: numpy scipy matplotlib opencv-python PIL.
"""
from __future__ import annotations
import json, csv, argparse, hashlib
from pathlib import Path
import numpy as np
from scipy.ndimage import map_coordinates, gaussian_filter
from scipy.optimize import minimize_scalar
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import cv2

WAVELENGTH_NM = {"R":617.,"G":520.,"B":449.}

def lca_diopters(lmbda_nm:float)->float:
    # Approximation given in Cholewiak et al. (2018), 520-nm reference.
    return 2.071 - 633.46/(lmbda_nm - 214.10)


def model_psf(defocus_D: float, wavelength_nm: float, pupil_mm: float=4.,
              distance_m: float=.6, pitch_mm: float=.27,
              n_fft: int=320, extent_mm: float=8.,
              kernel_size: int=49, subpixels: int=7)->np.ndarray:
    """Monochromatic diffraction PSF, integrated onto retinal-angle screen pixels.

    Eye treated as circular aperture with pure defocus; no higher-order
    aberrations, no scatter; wavelength-specific defocus is passed directly.
    The pupil is in the plane of the thin-lens approximation.
    """
    if kernel_size%2==0 or n_fft%2 or extent_mm < pupil_mm*1.3:
        raise ValueError('invalid computational geometry')
    dx_m=(extent_mm/1000)/n_fft
    grid=(np.arange(n_fft,dtype=np.float64)-n_fft/2)*dx_m
    y,x=np.meshgrid(grid,grid,indexing='ij')
    r2=x*x+y*y
    aperture=(r2 <= (pupil_mm/2000)**2).astype(np.float64)
    lam=wavelength_nm*1e-9
    # Optical path difference due to defocus D: W(r)=D*r^2/2; phase 2pi*W/lambda
    pupil_complex=aperture*np.exp(1j*np.pi*defocus_D*r2/lam)
    field=np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(pupil_complex)))
    intensity=(field.real**2+field.imag**2)
    # FFT angular-space sampling from Fraunhofer diffraction.
    theta_fft=lam/(extent_mm/1000)
    theta_px=(pitch_mm/1000)/distance_m
    offsets=(np.arange(subpixels)+.5)/subpixels-.5
    centers=np.arange(-(kernel_size//2), kernel_size//2+1, dtype=np.float64)
    u=(centers[:,None]+offsets[None,:]).reshape(-1)
    index=n_fft/2+u*theta_px/theta_fft
    yy,xx=np.meshgrid(index,index,indexing='ij')
    sampled=map_coordinates(intensity,[yy,xx],order=1,mode='constant',cval=0.,prefilter=False)
    psf=sampled.reshape(kernel_size,subpixels,kernel_size,subpixels).mean(axis=(1,3))
    psf=np.maximum(psf,0.)
    psf/=psf.sum()
    return psf


def convolve_gaussian_psf(baseline:np.ndarray,sigma:float)->np.ndarray:
    if sigma<1e-5:
        return baseline
    out=gaussian_filter(baseline,sigma,mode='constant',truncate=5.)
    out/=out.sum()
    return out


def error_metric(pred:np.ndarray,target:np.ndarray)->float:
    """L2-norm PSF error, normalized by L2 norm of target PSF."""
    return float(np.linalg.norm(pred-target)/np.linalg.norm(target))


def optimize_one(baseline:np.ndarray,target:np.ndarray,sigma_max:float=10.):
    f=lambda s:np.sum((convolve_gaussian_psf(baseline,s)-target)**2)
    opt=minimize_scalar(f,bounds=(0.,sigma_max),method='bounded',options={'xatol':1e-4})
    # non-monotone possibilities + endpoint; ensure best even if optimizer misses sigma~0.
    grid=np.linspace(0,sigma_max,101)
    grid_results=[(f(s),s) for s in grid]
    candidates=[(f(0.),0.),(f(sigma_max),sigma_max),(f(opt.x),float(opt.x)),min(grid_results)]
    _,sigma=min(candidates)
    return float(sigma)


def optimize_control(baselines:dict, targets:dict, sigma_max=10.):
    f=lambda s:sum(np.sum((convolve_gaussian_psf(baselines[c],s)-targets[c])**2)
                   for c in 'RGB')
    opt=minimize_scalar(f,bounds=(0.,sigma_max),method='bounded')
    candidates=[(f(s),float(s)) for s in np.linspace(0,sigma_max,101)]
    candidates += [(f(float(opt.x)),float(opt.x))]
    return float(min(candidates)[1])


def illustrate(results, psfs, out:Path, distance=.6, pitch=.27):
    # Overview diagram: PSF profiles of target (real-world), fixed focus (none),
    # optimized per-color, optimized shared-sigma control, for both directions.
    fig,axs=plt.subplots(2,3,figsize=(13,7),sharex=True)
    for ridx,(condition,data) in enumerate(results.items()):
        for cidx,c in enumerate('RGB'):
            ax=axs[ridx,cidx]
            baseline=psfs[(condition,c,'baseline')]
            target=psfs[(condition,c,'target')]
            color_fit=psfs[(condition,c,'lca')]
            control_fit=psfs[(condition,c,'control')]
            center=len(target)//2
            x=np.arange(-12,13)
            def profile(v):return v.sum(axis=0)[center-12:center+13]
            ax.plot(x,profile(target),'k-',lw=2,label='Target retinal PSF')
            ax.plot(x,profile(baseline),':',color='gray',label='Fixed screen, no blur')
            ax.plot(x,profile(control_fit),'--',color='#d17c26',label='Shared RGB blur')
            ax.plot(x,profile(color_fit),'-',color={'R':'#d95e61','G':'#319b6a','B':'#457ad5'}[c],lw=1.6,label='Per-color optimized blur')
            ax.set_title(f'{condition} / {c} | optimal sigma = {data["rgb_sigmas_px"][c]:.2f} px',fontsize=10)
            ax.set_xlabel('Retinal-angle-equivalent screen pixels')
            ax.set_ylabel('Integrated PSF profile')
            ax.grid(alpha=.16)
    handles,labels=axs[0,0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='upper center',ncol=4,fontsize=9,bbox_to_anchor=(.5,1.02))
    fig.suptitle('Fixed-screen wave-optics prediction — NOT measured eye response',y=1.065,fontsize=13)
    fig.tight_layout()
    fig.savefig(out/'psf_profiles.png',dpi=150,bbox_inches='tight')
    plt.close(fig)

    # Visualize hypothetical retinal appearance for each candidate.
    from PIL import ImageDraw
    rng=np.random.default_rng(812)
    h,w=210,420
    im=rng.normal(size=(h,w)).astype(np.float32)
    im=cv2.GaussianBlur(im,(0,0),1.3)
    im=(im-im.mean())/(im.std()+1e-6)
    im=np.clip(.53+.20*im,.1,.9)
    src=np.uint8(np.round(im*255))
    cv2.putText(src,'F  E  P  T  C', (25,128),cv2.FONT_HERSHEY_SIMPLEX,1.45,0,3,cv2.LINE_AA)
    cv2.line(src,(15,20),(w-20,20),20,2)
    cv2.rectangle(src,(15,160),(w-15,190),20,2)
    labels=[]
    panels=[]
    for condition in ('near','far'):
        for variant in ('target','baseline','control','lca'):
            rgb=np.zeros((h,w,3),dtype=np.uint8)
            for cidx,c in enumerate('RGB'):
                psf=psfs[(condition,c,variant)].astype(np.float32)
                rgb[:,:,cidx]=cv2.filter2D(src,-1,psf,borderType=cv2.BORDER_REFLECT_101)
            panels.append(rgb)
            labels.append(f'{condition.upper()} — {variant}')
    board=Image.new('RGB',(w*4,h*2+64*2),(249,249,250))
    from PIL import ImageDraw,ImageFont
    draw=ImageDraw.Draw(board)
    for i,p in enumerate(panels):
        xx=(i%4)*w; yy=(i//4)*(h+64)
        board.paste(Image.fromarray(p),(xx,yy+36))
        draw.text((xx+10,yy+10),labels[i],fill=(30,40,54))
    board.save(out/'predicted_retinal_images.png')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',type=Path,default=Path(__file__).resolve().parent)
    p.add_argument('--distance-m',type=float,default=.60)
    p.add_argument('--pitch-mm',type=float,default=.27)
    p.add_argument('--pupil-mm',type=float,default=4.)
    p.add_argument('--delta-D',type=float,default=.45)
    args=p.parse_args()
    if not(.3<=args.distance_m<=1.5 and .12<=args.pitch_mm<=.6 and 2<=args.pupil_mm<=6.5 and .15<=args.delta_D<=.85):
        raise ValueError('parameter outside exploratory bounds')
    args.out.mkdir(parents=True,exist_ok=True)
    records={}; storage={}
    for direction,delta in [('near',args.delta_D),('far',-args.delta_D)]:
        baselines={}; targets={}
        for c in 'RGB':
            wl=WAVELENGTH_NM[c]
            # Eye focus is assumed to be optimized at 520 nm; baseline chromatic
            # defocus is not zero for red/blue, even when the screen is in focus.
            baseline_d=lca_diopters(wl)
            baselines[c]=model_psf(baseline_d,wl,args.pupil_mm,args.distance_m,args.pitch_mm)
            targets[c]=model_psf(baseline_d+delta,wl,args.pupil_mm,args.distance_m,args.pitch_mm)
        s_control=optimize_control(baselines,targets)
        s_per={c:optimize_one(baselines[c],targets[c]) for c in 'RGB'}
        dct={'delta_D':delta,'rgb_sigmas_px':s_per,'shared_control_sigma_px':s_control,
             'channels':{},'total_rmse':{}}
        for c in 'RGB':
            b,t=baselines[c],targets[c]
            preds={'baseline':b,'control':convolve_gaussian_psf(b,s_control),
                   'lca':convolve_gaussian_psf(b,s_per[c]),'target':t}
            for variant,psf in preds.items():storage[(direction,c,variant)]=psf
            dct['channels'][c]={
                'wavelength_nm':WAVELENGTH_NM[c],
                'baseline_lca_D':round(lca_diopters(WAVELENGTH_NM[c]),5),
                'target_optical_error_D':round(lca_diopters(WAVELENGTH_NM[c])+delta,5),
                'relative_psf_errors':{v:round(error_metric(psf,t),6) for v,psf in preds.items() if v!='target'}
            }
        # Overall fit weighted by signal power in each channel, no clipping.
        for v in ('baseline','control','lca'):
            residual=sum(np.sum((storage[(direction,c,v)]-targets[c])**2) for c in 'RGB')
            targpow=sum(np.sum(targets[c]**2) for c in 'RGB')
            dct['total_rmse'][v]=round(float(np.sqrt(residual/targpow)),6)
        dct['improvement_over_control_percent']=round(100*(1-dct['total_rmse']['lca']/dct['total_rmse']['control']),2) if dct['total_rmse']['control'] else None
        records[direction]=dct
    config={
       'assumptions': 'ideal circular pupil + diffraction + quadratic defocus + simplified 3-primary LCA; no higher order eye aberrations, spectra, ocular scatter or person-to-person variations',
       'model_status':'COMPUTATIONAL PROOF OF CONCEPT ONLY; Not 2018 method replication, not validated against real optics or measured accommodation',
       'distance_m':args.distance_m, 'pitch_mm':args.pitch_mm,'pupil_mm':args.pupil_mm,
       'target_delta_D':args.delta_D,'fft_grid':320,'aperture_window_mm':8,'psf_kernel_size':49,'pixel_subsamples':7,
       'test_significance':'None. Errors here are deterministic simulation outputs, not statistical estimates or evidence of ciliary muscle response.',
    }
    output={'config':config,'results':records,'limitations':[
        'No monitor RGB spectral power distributions, measured luminance/gamma, accommodation response or individual ocular wavefront.',
        'Gaussian nonnegative blur cannot undo baseline chromatic blur; retinal targets may be physically unachievable using this restricted renderer.',
        'Simulated target PSF differs from retinal output if a real eye changes focus; open-loop reference assumption only.',
        'A sharp 2D screen always remains at its physical optical distance; stimulus is a depth-dependent blur cue, not a real 100 m focal plane.',
    ]}
    (args.out/'results.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    with (args.out/'metrics.csv').open('w',newline='') as f:
        writer=csv.writer(f)
        writer.writerow(['condition','delta_D','channel','LCA_D','target_error_D','optimized_sigma_px','control_sigma_px','baseline_relative_error','control_relative_error','lca_relative_error'])
        for condition,dct in records.items():
            for c,detail in dct['channels'].items():
                writer.writerow([condition,dct['delta_D'],c,detail['baseline_lca_D'],detail['target_optical_error_D'],
                                round(dct['rgb_sigmas_px'][c],4),round(dct['shared_control_sigma_px'],4),
                                detail['relative_psf_errors']['baseline'],detail['relative_psf_errors']['control'],detail['relative_psf_errors']['lca']])
    illustrate(records,storage,args.out,args.distance_m,args.pitch_mm)
    for condition,dct in records.items():
        print(condition, 'target delta:',dct['delta_D'], 'sigma per channel:',dct['rgb_sigmas_px'], 'common control:',round(dct['shared_control_sigma_px'],4))
        print('   overall normalized RMSE',dct['total_rmse'],'relative improvement over control',dct['improvement_over_control_percent'],'%')
    print('files:',[p.name for p in args.out.glob('*')])

if __name__=='__main__':
    main()