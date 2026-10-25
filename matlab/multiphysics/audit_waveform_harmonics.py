"""Audit saved full-rate simulations; never use display samples for THD."""
from pathlib import Path
import json
import numpy as np
from scipy.io import loadmat
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'outputs' / 'waveform_audit'
OUT.mkdir(exist_ok=True)
CASES = ['electrical_reference', 'electrical_reference_200',
         'electrical_reference_400', 'electrical_reference_800',
         'electrical_reference_400_candidate74',
         'electrical_reference_400_E70FE68_500W',
         'electrical_reference_400_E70FE68_750W']
CASES += [p.name for p in sorted((ROOT/'outputs').glob('electrical_reference*'))
          if p.name not in CASES and (p.name == 'electrical_reference_1600'
          or p.name.startswith('electrical_reference_800_E70FE68_'))
          and (p/'handoff_local.json').exists()]
rows = []
for name in CASES:
    folder = ROOT / 'outputs' / name
    d = loadmat(folder / 'simulation.mat')
    t, y = d['t'].ravel(), d['y']
    dt = float(t[1]-t[0])
    n = round(.08/dt)
    x = y[-n-1:-1, :2]
    z = np.fft.rfft(x, axis=0)/n
    amp = 2*np.abs(z)
    freq = np.fft.rfftfreq(n, dt)
    fund_rms = amp[4]/np.sqrt(2)
    thd = 100*np.sqrt(np.sum(amp[np.arange(2,41)*4]**2, axis=0))/amp[4]
    ac_power = np.mean((x-np.mean(x,axis=0))**2,axis=0)
    spectral_power = 2*np.sum(np.abs(z[1:-1])**2,axis=0)+np.abs(z[-1])**2
    assert np.allclose(ac_power,spectral_power,rtol=1e-10,atol=1e-12), 'FFT energy mismatch'
    nonfund = 100*np.sqrt(np.maximum(0,ac_power-fund_rms**2))/fund_rms
    high = 100*np.sqrt(np.sum(amp[(freq>2000)&(freq<freq[-1])]**2,axis=0)/2)/fund_rms
    common_band = 100*np.sqrt(np.sum(amp[(freq>2000)&(freq<=200000)]**2,axis=0)/2)/fund_rms
    step = round(1/20000/dt)
    blocks = x[:,1].reshape(-1,step)
    means = blocks.mean(axis=1)
    cyclemeans = means.reshape(4,400)
    row = dict(case=name, samples_per_switch=step,
               voltage_thd_2_40_percent=float(thd[0]), current_thd_2_40_percent=float(thd[1]),
               voltage_nonfundamental_to_nyquist_percent=float(nonfund[0]),
               current_nonfundamental_to_nyquist_percent=float(nonfund[1]),
               current_above_2kHz_percent=float(high[1]),
               current_2kHz_to_200kHz_percent=float(common_band[1]),
               current_rms_A=float(np.sqrt(np.mean(x[:,1]**2))),
               current_peak_A=float(np.max(np.abs(x[:,1]))),
               nyquist_Hz=float(freq[-1]),
               current_fundamental_rms_A=float(fund_rms[1]),
               current_period_ripple_rms_A=float(np.sqrt(np.mean((blocks-means[:,None])**2))),
               mean_current_cycle_max_difference_A=float(np.max(np.ptp(cyclemeans,axis=0))))
    ref = json.loads((folder/'result.json').read_text(encoding='utf-8'))
    row['output_rms_V'] = ref['metrics']['output_rms']
    row['winding_Rdc_loss_W'] = ref['metrics']['winding_loss']
    if name in ['electrical_reference_400','electrical_reference_800','electrical_reference_1600']:
        from scipy.integrate import cumulative_trapezoid
        raw = y[-n-1:-1]
        vl = raw[:,3]-raw[:,0]-ref['spec']['winding_resistance']*raw[:,1]
        linkage = ref['spec']['inductance']*raw[:,1]
        residual = cumulative_trapezoid(vl,dx=dt,initial=0)-linkage
        residual -= residual.mean()
        row['flux_residual_rms_percent_of_peak'] = float(100*np.sqrt(np.mean(residual**2))/np.max(np.abs(linkage)))
        row['flux_residual_max_mWb_turn'] = float(1000*np.max(np.abs(residual)))
    assert abs(thd[0]-ref['metrics']['thd_percent'])<1e-8
    rows.append(row)
    if name == 'electrical_reference_200':
        idx = np.unique(np.floor(np.linspace(0,len(t)-1,3200)+.5).astype(int))
        tb = t[-n-1:-1].reshape(-1,step).mean(axis=1)
        fig, ax = plt.subplots(3,1,figsize=(12,9), constrained_layout=True)
        pick = t[idx]>=.16
        ax[0].plot(t[idx][pick],y[idx,1][pick],lw=.8,label='Original 3200-point display sampling')
        ax[0].plot(tb,means,'k',lw=1.1,label='Switch-period mean (not instantaneous current)')
        ax[0].set(title='Same raw data: apparent slow envelope depends on display sampling',ylabel='Current (A)')
        ax[0].legend(fontsize=9)
        ax[1].fill_between(tb,blocks.min(axis=1),blocks.max(axis=1),alpha=.35,label='True per-period min/max')
        ax[1].plot(tb,means,'k',lw=1,label='Switch-period mean')
        ax[1].set(xlim=(.22,.24),ylabel='Current (A)',title='Final cycle: preserved ripple envelope')
        ax[1].legend(fontsize=9)
        pick=(t>=.224)&(t<=.2242)
        ax[2].plot(t[pick],y[pick,1],lw=.9)
        ax[2].set(ylabel='Current (A)',xlabel='Time (s)',title='Four switching periods: full-rate samples')
        for a in ax: a.grid(alpha=.3)
        fig.savefig(OUT/'sampling_audit.png',dpi=160)
        plt.close(fig)
        fig,ax=plt.subplots(2,1,figsize=(11,7),constrained_layout=True)
        for j,label in enumerate(['Output voltage','Inductor current']):
            keep=(freq>=50)&(freq<=100000)
            ax[j].semilogx(freq[keep],20*np.log10(np.maximum(amp[keep,j]/amp[4,j],1e-9)),lw=.6)
            ax[j].set(xlabel='Frequency (Hz)',ylabel='Amplitude (dBc)',ylim=(-120,5),title=label+' | full-rate FFT, final four cycles')
            ax[j].axvline(2000,color='r',ls='--',lw=.8)
            ax[j].grid(alpha=.3)
        fig.savefig(OUT/'full_rate_spectrum.png',dpi=160)
        plt.close(fig)
(OUT/'metrics.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
base = [r for r in rows if r['case'] in ['electrical_reference',
        'electrical_reference_200','electrical_reference_400',
        'electrical_reference_800','electrical_reference_1600']]
base.sort(key=lambda r:r['samples_per_switch'])
fig,ax=plt.subplots(1,2,figsize=(11,4),constrained_layout=True)
steps=[r['samples_per_switch'] for r in base]
ax[0].plot(steps,[r['voltage_thd_2_40_percent'] for r in base],'o-',label='Output voltage')
ax[0].plot(steps,[r['current_thd_2_40_percent'] for r in base],'s-',label='Inductor current')
ax[0].set(xlabel='Steps per switching period',ylabel='THD, orders 2-40 (%)')
ax[0].legend()
flux=[r for r in base if 'flux_residual_rms_percent_of_peak' in r]
ax[1].plot([r['samples_per_switch'] for r in flux],
           [r['flux_residual_rms_percent_of_peak'] for r in flux],'o-')
ax[1].set(xlabel='Steps per switching period',ylabel='Flux residual RMS / peak linkage (%)')
for a in ax: a.grid(alpha=.3)
fig.savefig(OUT/'step_refinement.png',dpi=160)
plt.close(fig)
print(json.dumps(rows,indent=2))
