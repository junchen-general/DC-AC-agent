function result = dcac_postprocess(simulation,s,e,context,outdir,result)
%DCAC_POSTPROCESS Export legacy data plus a self-describing B-to-C package.
ts=simulation.get('dcac_signals');
t=ts.Time(:); y=squeeze(ts.Data);
if size(y,1)~=numel(t), y=y.'; end
if size(y,2)<15
    error('DCAC:Signals','Expected 15 recorded channels, found %d.',size(y,2));
end
if any(~isfinite(t)) || any(~isfinite(y(:))) || any(diff(t)<=0)
    error('DCAC:Invalid','Simulation contains nonfinite or nonmonotonic results.');
end
dtMedian=median(diff(t));
uniformError=max(abs(diff(t)-dtMedian))/max(dtMedian,eps);
if uniformError>1e-6
    error('DCAC:Sampling','Recorded time base is not uniform enough for the declared FFT analysis.');
end
requestedStepError=abs(dtMedian-e.fixed_step_s)/max(e.fixed_step_s,eps);
if requestedStepError>1e-6
    error('DCAC:Sampling','Logged sample time does not match requested fixed step (relative error %.3g).',requestedStepError);
end

signalNames={'v_out_V','i_inductor_A','i_load_A','v_bridge_V', ...
    'v_inductor_terminal_V','v_winding_resistive_V','v_inductive_V', ...
    'i_capacitor_A','load_conductance_S','gate_a_upper','gate_a_lower', ...
    'gate_b_upper','gate_b_lower','i_dc_A','v_dc_V'};
signals=struct;
for k=1:numel(signalNames), signals.(signalNames{k})=y(:,k); end
signals.p_winding_resistive_W=signals.i_inductor_A.^2*s.winding_resistance;
signals.sample_index_0based=(0:numel(t)-1).';
signals.time_s=t;

analysisEnd=t(end);
analysisStart=analysisEnd-4/s.output_frequency;
steady=find(t>=analysisStart-0.1*dtMedian & t<analysisEnd-0.1*dtMedian);
expected=round(4/s.output_frequency/dtMedian);
if numel(steady)~=expected
    error('DCAC:Window','Expected %d samples in the final four-cycle window, found %d.',expected,numel(steady));
end
v=signals.v_out_V(steady); il=signals.i_inductor_A(steady); io=signals.i_load_A(steady);
ic=signals.i_capacitor_A(steady); vl=signals.v_inductor_terminal_V(steady);
vind=signals.v_inductive_V(steady); idc=signals.i_dc_A(steady); vdc=signals.v_dc_V(steady);

[harmonicNumbers,harmonicAmps,thd,switchingBandRms,widebandResidualRms]= ...
    spectralMetrics(t(steady),v,s.output_frequency,s.switching_frequency,dtMedian);
rmsV=rmsValue(v); rmsIL=rmsValue(il); rmsIO=rmsValue(io);
fundamentalFit=[sin(2*pi*s.output_frequency*t(steady)) cos(2*pi*s.output_frequency*t(steady)) ones(numel(steady),1)]\il;
ilRipple=il-[sin(2*pi*s.output_frequency*t(steady)) cos(2*pi*s.output_frequency*t(steady)) ones(numel(steady),1)]*fundamentalFit;

metrics=struct('output_rms',rmsV,'current_rms',rmsIO, ...
    'inductor_rms',rmsIL,'inductor_peak',max(abs(il)), ...
    'output_power',mean(v.*io),'winding_loss',mean(il.^2)*s.winding_resistance, ...
    'thd_percent',thd,'voltage_error_percent',100*(rmsV/s.output_voltage-1), ...
    'analysis_cycles',4,'harmonic_max',40,'sample_time',dtMedian, ...
    'analysis_start',t(steady(1)),'analysis_end',analysisEnd, ...
    'analysis_end_exclusive',analysisEnd);

electricalMetrics=struct( ...
    'thd_h2_h40_percent',thd, ...
    'thd_definition','2nd through 40th integer multiples of the fundamental; carrier band excluded', ...
    'switching_bands_hz',[0.5*s.switching_frequency 1.5*s.switching_frequency; ...
        1.5*s.switching_frequency 2.5*s.switching_frequency], ...
    'switching_band_rms_V',switchingBandRms, ...
    'switching_band_note','Both fsw and 2*fsw neighborhoods are reported because the differential unipolar bridge can concentrate ripple near 2*fsw.', ...
    'wideband_residual_rms_V',widebandResidualRms, ...
    'inductor_min_A',min(il),'inductor_max_A',max(il), ...
    'inductor_nonfundamental_residual_pp_A',max(ilRipple)-min(ilRipple), ...
    'inductor_residual_definition','peak-to-peak after least-squares removal of DC and 50 Hz only; includes harmonics and switching ripple', ...
    'capacitor_rms_A',rmsValue(ic), ...
    'inductor_terminal_rms_V',rmsValue(vl), ...
    'inductor_terminal_peak_V',max(abs(vl)), ...
    'inductive_voltage_rms_V',rmsValue(vind), ...
    'inductive_voltage_peak_V',max(abs(vind)), ...
    'dc_input_power_W',mean(vdc.*idc), ...
    'load_output_power_W',mean(v.*io));

dynamic=struct;
if isStepScenario(e.scenario_id)
    transient=t>=s.load_step_time & t<min(analysisStart,s.load_step_time+0.04);
    cycleSamples=max(1,round(1/s.output_frequency/dtMedian));
    movingVrms=sqrt(movmean(signals.v_out_V.^2,[cycleSamples-1 0]));
    after=find(t>=s.load_step_time+1/s.output_frequency);
    errorBand=abs(movingVrms(after)-rmsV)<=0.02*max(rmsV,eps);
    settle=NaN;
    for k=1:numel(after)
        if all(errorBand(k:end)), settle=t(after(k))-s.load_step_time; break; end
    end
    dynamic=struct('step_time_s',s.load_step_time, ...
        'transient_inductor_peak_A',max(abs(signals.i_inductor_A(transient))), ...
        'transient_output_voltage_peak_V',max(abs(signals.v_out_V(transient))), ...
        'one_cycle_rms_max_after_step_V',max(movingVrms(after)), ...
        'one_cycle_rms_min_after_step_V',min(movingVrms(after)), ...
        'settling_time_2pct_s',settle, ...
        'settling_definition','first one-cycle RMS point after which all remaining points stay within 2% of final-window RMS');
end

losses=lossLedger(s,e,steady,signals,metrics);
windows=windowLedger(t,s,e,steady);
meta=struct('schema_version','dcac.electrical.raw/1.0','data_origin','real_simulation', ...
    'model_fidelity',e.model_fidelity,'scenario_id',e.scenario_id,'run_context',context, ...
    'legacy_y_columns',{{'Vout_V','IL_A','Iload_A','Vbridge_V'}}, ...
    'sampling',struct('solver',e.solver_name,'solver_type',e.solver_type, ...
    'fixed_step_s',e.fixed_step_s,'logging_sample_time_s',dtMedian, ...
    'sample_count',numel(t),'decimation',1,'is_uniform',uniformError<=1e-6, ...
    'max_relative_step_deviation',uniformError,'requested_step_relative_error',requestedStepError, ...
    'dt_min_s',min(diff(t)),'dt_max_s',max(diff(t)), ...
    't_start_s',t(1),'t_end_s',t(end)));

yFull=y;
y=yFull(:,1:4); %#ok<NASGU> Legacy contract: exactly [Vout, IL, Iload, Vbridge].
if e.export_legacy_mat
    save(fullfile(outdir,'simulation.mat'),'t','y','s','-v7');
end
y=yFull;
save(fullfile(outdir,'electrical_raw_v1.mat'),'t','s','e','context','meta', ...
    'signals','windows','metrics','electricalMetrics','dynamic','losses','-v7');
if e.export_legacy_csv
    writematrix([t y(:,1:4)],fullfile(outdir,'signals.csv'));
end
if e.export_full_csv
    tableData=table(signals.sample_index_0based,t,signals.i_inductor_A,signals.v_bridge_V, ...
        signals.v_out_V,signals.i_load_A,signals.load_conductance_S, ...
        signals.v_inductor_terminal_V,signals.v_winding_resistive_V, ...
        signals.v_inductive_V,signals.i_capacitor_A,signals.p_winding_resistive_W, ...
        signals.gate_a_upper,signals.gate_a_lower,signals.gate_b_upper,signals.gate_b_lower, ...
        signals.i_dc_A,signals.v_dc_V, ...
        'VariableNames',{'sample_index_0based','time_s','i_inductor_A','v_bridge_V', ...
        'v_out_V','i_load_A','load_conductance_S','v_inductor_terminal_V', ...
        'v_winding_resistive_V','v_inductive_V','i_capacitor_A', ...
        'p_winding_resistive_W','gate_a_upper','gate_a_lower','gate_b_upper', ...
        'gate_b_lower','i_dc_A','v_dc_V'});
    writetable(tableData,fullfile(outdir,'electrical_full_v1.csv'));
end
dcac_write_json(fullfile(outdir,'loss_basis_v1.json'),dcac_loss_basis(e));

result.metrics=metrics;
result.checks=struct('voltage',abs(metrics.voltage_error_percent)<=5,'thd',thd<5);
result.electrical_v1.metrics=electricalMetrics;
result.electrical_v1.dynamic=dynamic;
result.electrical_v1.losses=losses;
result.electrical_v1.sampling=meta.sampling;
result.electrical_v1.windows=windows;
result.electrical_v1.full_resolution_files={'electrical_raw_v1.mat'};
if e.export_full_csv
    result.electrical_v1.full_resolution_files{end+1}='electrical_full_v1.csv';
end
result.electrical_v1.data_origin='real_simulation';
idx=unique(round(linspace(1,numel(t),min(3200,numel(t)))));
result.waveforms=struct('time',t(idx).','voltage',signals.v_out_V(idx).', ...
    'inductor_current',signals.i_inductor_A(idx).','load_current',signals.i_load_A(idx).');
result.harmonics=struct('order',harmonicNumbers.','amplitude',harmonicAmps.', ...
    'frequency_hz',(harmonicNumbers*s.output_frequency).');
result.analysis_notes={ ...
    'Actual Simulink result. Web JSON waveforms are display-only decimation; C must use the full MAT/CSV.', ...
    sprintf('Model fidelity: %s; scenario: %s.',e.model_fidelity,e.scenario_id), ...
    'Legacy THD is harmonics 2 through 40 over the final four whole cycles; it excludes the carrier band.', ...
    'Winding I^2R is a constant-R DC-ohmic estimate. It is not total inverter loss or whole-inverter efficiency.', ...
    'Device loss parameters and limitations are recorded in loss_basis_v1.json.'};
makePlot(outdir,t,signals,idx,rmsV,thd);
end

function losses=lossLedger(s,e,steady,signals,metrics)
losses=struct;
losses.winding_dc_ohmic=struct('value_W',metrics.winding_loss,'status','assumed_unverified', ...
    'method','mean(iL^2)*constant winding_resistance','resistance_ohm',s.winding_resistance, ...
    'temperature_C',[],'window_id','thd_steady','basis_ref','spec.winding_resistance', ...
    'source',struct('kind','unspecified','status','assumed_unverified'), ...
    'included_in_whole_inverter_efficiency',false);
if contains(e.model_fidelity,'lossy') || contains(e.model_fidelity,'closed_loop')
    il=signals.i_inductor_A(steady);
    conduction=2*e.device_rds_on_ohm*mean(il.^2);
    switching=2*s.input_voltage*mean(abs(il))*(e.device_rise_time_s+e.device_fall_time_s)*s.switching_frequency;
    diodeDead=4*e.device_diode_vf_v*mean(abs(il))*e.dead_time_s*s.switching_frequency;
    reverseRecoveryReference=4*s.input_voltage*e.device_reverse_recovery_charge_c*s.switching_frequency;
    basisRef=struct('file','loss_basis_v1.json','parameter_source_status',e.device_parameter_source_status);
    losses.semiconductor_conduction=struct('value_W',conduction,'status','preliminary_datasheet_scaled', ...
        'window_id','thd_steady','basis_ref',basisRef);
    losses.switching_overlap=struct('value_W',switching,'status','preliminary_overlap_model', ...
        'window_id','thd_steady','basis_ref',basisRef);
    losses.dead_time_diode=struct('value_W',diodeDead,'status','preliminary_dead_time_model', ...
        'window_id','thd_steady','basis_ref',basisRef);
    losses.reverse_recovery_reference_not_included=struct('value_W',reverseRecoveryReference, ...
        'status','datasheet_test_point_not_scaled_to_operating_current', ...
        'window_id','thd_steady','basis_ref',basisRef);
    losses.total_modeled_electrical_loss=struct('value_W',metrics.winding_loss+conduction+switching+diodeDead, ...
        'window_id','thd_steady','status','partial_not_efficiency');
    losses.completeness='partial; excludes core, capacitor ESR, gate drive, controls, auxiliaries and thermal iteration';
else
    losses.completeness='winding DC-ohmic term only';
end
losses.whole_inverter_efficiency_claimed=false;
end

function windows=windowLedger(t,s,e,steady)
windows=struct('id',{},'purpose',{},'start_time_s',{},'last_sample_time_s',{}, ...
    'end_time_exclusive_s',{}, ...
    'end_exclusive',{},'start_index_0based',{},'end_index_exclusive_0based',{}, ...
    'sample_count',{},'fundamental_cycles',{},'load_state',{},'selected_for_c',{},'selection_reason',{});
windows(end+1)=window('full_run','all recorded samples',1,numel(t),t,s,e,'full',false,'Retained for transient traceability.');
windows(end+1)=window('thd_steady','legacy THD and steady metrics',steady(1),steady(end),t,s,e, ...
    finalLoad(e),true,'Final four complete cycles with full switching ripple.');
cycleSamples=round(1/s.output_frequency/median(diff(t)));
cycleStart=steady(end)-cycleSamples+1;
if cycleStart<steady(1) || steady(end)-cycleStart+1~=cycleSamples
    error('DCAC:Window','Unable to select exactly one representative fundamental cycle.');
end
windows(end+1)=window('magnetic_representative','one final fundamental cycle for magnetic analysis', ...
    cycleStart,steady(end),t,s,e,finalLoad(e),true,'Full-resolution current and induced voltage; no decimation.');
if isStepScenario(e.scenario_id)
    pre=find(t>=s.load_step_time-2/s.output_frequency & t<s.load_step_time);
    trans=find(t>=s.load_step_time & t<min(s.load_step_time+0.04,t(end)));
    windows(end+1)=window('pre_step','pre-step steady state',pre(1),pre(end),t,s,e,'rated',true,'Two cycles before load change.');
    windows(end+1)=window('transient','load-step transient',trans(1),trans(end),t,s,e,e.scenario_id,true,'Captures peak current and voltage excursion.');
    windows(end+1)=window('post_step','post-step steady state',steady(1),steady(end),t,s,e,finalLoad(e),true,'Same samples as final THD window.');
end
end

function out=window(id,purpose,i0,i1,t,s,~,state,selected,reason)
dt=median(diff(t));
out=struct('id',id,'purpose',purpose,'start_time_s',t(i0), ...
    'last_sample_time_s',t(i1),'end_time_exclusive_s',t(i1)+dt, ...
    'end_exclusive',true,'start_index_0based',i0-1,'end_index_exclusive_0based',i1, ...
    'sample_count',i1-i0+1,'fundamental_cycles',(i1-i0+1)*dt*s.output_frequency, ...
    'load_state',state,'selected_for_c',selected,'selection_reason',reason);
end

function yes=isStepScenario(value)
yes=strcmp(value,'rated_to_half') || strcmp(value,'load_step');
end

function state=finalLoad(e)
if abs(e.load_ratio_final-0.5)<1e-12
    state='half_load';
elseif abs(e.load_ratio_final-1)<1e-12
    state='rated';
else
    state=sprintf('load_ratio_%.6g',e.load_ratio_final);
end
end

function [orders,amps,thd,switchingBandRms,residualRms]=spectralMetrics(t,v,f0,fsw,dt)
orders=(1:40).'; n=numel(v); localT=t-t(1);
amps=zeros(size(orders));
for k=1:numel(orders)
    amps(k)=2*abs(sum(v.*exp(-1i*2*pi*orders(k)*f0*localT)))/n;
end
thd=100*sqrt(sum(amps(2:end).^2))/max(amps(1),eps);
centered=v-mean(v); spectrum=fft(centered); single=2*abs(spectrum(1:floor(n/2)+1))/n;
single(1)=single(1)/2; frequencies=(0:floor(n/2)).'/(n*dt);
bands=[0.5 1.5;1.5 2.5]*fsw;
switchingBandRms=zeros(1,size(bands,1));
for b=1:size(bands,1)
    selected=frequencies>=bands(b,1) & frequencies<=bands(b,2);
    switchingBandRms(b)=sqrt(sum(single(selected).^2)/2);
end
harmonicMask=false(size(frequencies));
resolution=1/(n*dt);
for h=1:40, harmonicMask=harmonicMask | abs(frequencies-h*f0)<=0.51*resolution; end
wide=frequencies>0 & frequencies<=min(frequencies(end),2.5*fsw) & ~harmonicMask;
residualRms=sqrt(sum(single(wide).^2)/2);
end

function value=rmsValue(x)
value=sqrt(mean(x.^2));
end

function makePlot(outdir,t,signals,idx,rmsV,thd)
try
    f=figure('Visible','off','Color','w','Position',[100 100 1150 760]);
    tiledlayout(3,1);
    nexttile; plot(t(idx),signals.v_out_V(idx),'Color',[0.12 0.5 0.4]); grid on;
    ylabel('Vout (V)'); title(sprintf('%.2f Vrms | THD h2-h40 %.3f%%',rmsV,thd));
    nexttile; plot(t(idx),signals.i_inductor_A(idx),'Color',[0.15 0.35 0.65]); grid on;
    ylabel('iL (A)');
    nexttile; plot(t(idx),signals.v_inductive_V(idx),'Color',[0.65 0.3 0.18]); grid on;
    ylabel('vL induced (V)'); xlabel('Time (s)');
    exportgraphics(f,fullfile(outdir,'waveforms.png'),'Resolution',160); close(f);
catch plotError
    warning('DCAC:Plot','Waveform plot failed: %s',plotError.message);
end
end
