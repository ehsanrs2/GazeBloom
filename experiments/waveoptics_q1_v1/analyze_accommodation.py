#!/usr/bin/env python3
"""Analyze *measured* dynamic accommodation, once a calibrated instrument exists.

Input CSV columns: condition,trial_id,time_s,stimulus_D,measured_D,valid
`measured_D` must be objective accommodation in diopters, calibrated to an
increasing-near convention and corrected for instrument bias. This script
cannot establish accommodation from subjective responses, webcam signals, etc.

For each trial, fit sin + cos + intercept to the stimulus and response at the
specified temporal frequency. Output gain, phase lag, and in-phase gain. The
phase is only meaningful when response amplitude exceeds the noise floor.
No inferential p-values are calculated. Noise floor and stats must be handled
in the preregistered protocol using participant/trial structure.
"""
import argparse,csv,math
from collections import defaultdict
from pathlib import Path
import numpy as np

def fit_harmonic(t,y,freq):
    omega=2*math.pi*freq
    X=np.column_stack((np.sin(omega*t),np.cos(omega*t),np.ones_like(t)))
    p=np.linalg.lstsq(X,y,rcond=None)[0]
    amp=float(np.hypot(p[0],p[1]))
    phase=float(math.atan2(p[1],p[0]))
    yhat=X@p
    ss_tot=float(((y-y.mean())**2).sum())
    r2=1-float(((y-yhat)**2).sum())/ss_tot if ss_tot>0 else 0.
    return amp,phase,r2

def analyze_file(src:Path,dest:Path,freq:float,min_samples:int=60):
    groups=defaultdict(list)
    with src.open(newline='') as f:
        for r in csv.DictReader(f):
            if str(r.get('valid','1')).strip().lower() in ('0','false','no'):
                continue
            try:
                t=float(r['time_s']);s=float(r['stimulus_D']);y=float(r['measured_D'])
            except (ValueError,KeyError):
                continue
            if not all(math.isfinite(v) for v in (t,s,y)):
                continue
            groups[(r['condition'],r['trial_id'])].append((t,s,y))
    out=[]
    for (cond,trial),v in sorted(groups.items()):
        a=np.asarray(sorted(v),dtype=float)
        if len(a)<min_samples or np.ptp(a[:,0])<1/freq:
            continue
        stim_amp,stim_phase,stim_r2=fit_harmonic(a[:,0],a[:,1],freq)
        obs_amp,obs_phase,obs_r2=fit_harmonic(a[:,0],a[:,2],freq)
        if stim_amp<.02 or stim_r2<.85:
            continue
        # Phase response minus phase stimulus; wrapped to [-pi,+pi].
        dphase=math.atan2(math.sin(obs_phase-stim_phase),math.cos(obs_phase-stim_phase))
        gain=obs_amp/stim_amp
        in_phase_gain=gain*math.cos(dphase)
        lag_s=-dphase/(2*math.pi*freq)
        out.append({'condition':cond,'trial_id':trial,'sample_count':len(a),
                    'observed_duration_s':round(np.ptp(a[:,0]),3),
                    'frequency_Hz':freq,'stimulus_amplitude_D':round(stim_amp,5),
                    'response_amplitude_D':round(obs_amp,5),
                    'gain':round(gain,5),'in_phase_gain':round(in_phase_gain,5),
                    'phase_lag_deg':round(-math.degrees(dphase),3),
                    'phase_lag_s':round(lag_s,4),'response_r2':round(obs_r2,5),
                    'stimulus_r2':round(stim_r2,5)})
    dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open('w',newline='') as f:
        cols=['condition','trial_id','sample_count','observed_duration_s',
              'frequency_Hz','stimulus_amplitude_D','response_amplitude_D',
              'gain','in_phase_gain','phase_lag_deg','phase_lag_s',
              'response_r2','stimulus_r2']
        writer=csv.DictWriter(f,fieldnames=cols)
        writer.writeheader();writer.writerows(out)
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input_csv',type=Path)
    p.add_argument('--out',type=Path,default=Path('accommodation_fit.csv'))
    p.add_argument('--frequency-Hz',type=float,required=True)
    args=p.parse_args()
    if not 0.02<=args.frequency_Hz<=1.:
        raise ValueError('experimental frequency out of allowed bounds')
    res=analyze_file(args.input_csv,args.out,args.frequency_Hz)
    print('Analyzed valid trials:',len(res))
    print('Output:',args.out)
    if res:
        for c in sorted(set(r['condition'] for r in res)):
            gains=[r['in_phase_gain'] for r in res if r['condition']==c]
            print(f'{c}: {len(gains)} trials, mean in-phase gain={np.mean(gains):.3f} (NOT significance-tested)')

if __name__=='__main__':
    main()