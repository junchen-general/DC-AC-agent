function result = analyze_switching_ripple()
% Extract period-wise switching ripple from the full-rate candidate waveform.
% B is inferred from the linear circuit L/(N*Ae), not from nonlinear FEA.
root = fileparts(mfilename('fullpath'));
folder = fullfile(root,'outputs','electrical_reference_400_candidate74');
d = load(fullfile(folder,'simulation.mat'));
report = jsondecode(fileread(fullfile(folder,'handoff_local.json')));
material = jsondecode(fileread(fullfile(root,'material_assumptions.json')));
turns = material.winding_screening.turns;
ae = material.winding_screening.catalog_effective_core_area_m2;
fsw = report.spec.switching_frequency;
fout = report.spec.output_frequency;
dt = report.metrics.sample_time;
samplesPerSwitch = round(1/fsw/dt);
switchesPerCycle = round(fsw/fout);
numSwitches = 4*switchesPerCycle;
n = numSwitches*samplesPerSwitch;
assert(abs(samplesPerSwitch*dt*fsw-1)<1e-10);
assert(numel(d.t)>n && abs(d.t(end-n)-0.16)<1e-9);
il = reshape(d.y(end-n:end-1,2),samplesPerSwitch,numSwitches);
t = reshape(d.t(end-n:end-1),samplesPerSwitch,numSwitches);
periodMean = mean(il,1);
periodPp = max(il,[],1)-min(il,[],1);
ripple = il-periodMean;
periodRippleRms = sqrt(mean(ripple.^2,1));
sortPp = sort(periodPp);
per95 = sortPp(ceil(0.95*numel(sortPp)));
L = report.spec.inductance;
r = report.spec.winding_resistance;
BperA = L/(turns*ae);
rippleLoss = r*mean(ripple(:).^2);
totalLoss = r*mean(il(:).^2);
assert(abs(totalLoss/report.metrics.winding_loss-1)<1e-8);
result = struct('status','linear_circuit_screening_not_measured_core_loss', ...
    'case_name','electrical_reference_400_candidate74', ...
    'full_rate_samples_per_switch',samplesPerSwitch, ...
    'switching_periods_analyzed',numSwitches, ...
    'time_window_s',[t(1,1),t(end,end)], ...
    'period_current_pp_mean_A',mean(periodPp), ...
    'period_current_pp_median_A',median(periodPp), ...
    'period_current_pp_p95_A',per95, ...
    'period_current_pp_max_A',max(periodPp), ...
    'period_current_pp_min_A',min(periodPp), ...
    'period_B_pp_mean_T',BperA*mean(periodPp), ...
    'period_B_pp_p95_T',BperA*per95, ...
    'period_B_pp_max_T',BperA*max(periodPp), ...
    'B_per_A_from_L_N_Ae_T_per_A',BperA, ...
    'within_period_ripple_current_rms_A',sqrt(mean(ripple(:).^2)), ...
    'fixed_R_ohmic_loss_due_to_within_period_ripple_W',rippleLoss, ...
    'fixed_R_total_ohmic_loss_W',totalLoss, ...
    'fixed_R_ripple_loss_fraction',rippleLoss/totalLoss, ...
    'loss_note','Rdc decomposition only; does not estimate skin, proximity, fringing or core loss', ...
    'loop_note','Switching-period peak-to-peak envelope is not a counted minor B-H loop');
fid=fopen(fullfile(root,'outputs','switching_ripple.json'),'w','n','UTF-8');
fprintf(fid,'%s',jsonencode(result,PrettyPrint=true)); fclose(fid);
f=figure('Visible','off','Color','w','Position',[50 50 1100 650]);
last=(numSwitches-switchesPerCycle+1):numSwitches;
subplot(2,1,1);
plot(t(1,last),periodMean(last),'Color',[.1 .3 .6]); grid on;
ylabel('Mean i_L per switch (A)'); title('74-turn candidate, final 50 Hz cycle');
subplot(2,1,2);
plot(t(1,last),1000*BperA*periodPp(last),'Color',[.7 .25 .1]); grid on;
ylabel('Switch-period B peak-to-peak (mT)'); xlabel('Time (s)');
title('Linear B = L i / (N A_e); range within each switching period');
exportgraphics(f,fullfile(root,'outputs','switching_ripple.png'),'Resolution',160);
close(f);
disp(result);
end
