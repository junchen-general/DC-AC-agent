function results = analyze_flux_linkage()
% Reconstruct flux linkage from full-rate circuit waveforms.
% This verifies the ideal circuit state equation, not a measured B-H curve.
root = fileparts(mfilename('fullpath'));
cases = {'electrical_reference_400','electrical_reference_800', ...
    'electrical_reference_400_candidate74'};
resultsCell = cell(1,numel(cases));
for k = 1:numel(cases)
    folder = fullfile(root,'outputs',cases{k});
    d = load(fullfile(folder,'simulation.mat'));
    report = jsondecode(fileread(fullfile(folder,'handoff_local.json')));
    t = d.t(:); y = d.y;
    dt = report.metrics.sample_time;
    samplesPerCycle = round(1/report.spec.output_frequency/dt);
    n = 4*samplesPerCycle;
    idx = (numel(t)-n):(numel(t)-1);
    assert(numel(idx)==n && idx(1)>0);
    tt = t(idx); il = y(idx,2);
    vL = y(idx,4)-y(idx,1)-report.spec.winding_resistance*il;
    lambdaFromVoltage = cumtrapz(tt,vL);
    lambdaFromState = report.spec.inductance*il;
    offset = mean(lambdaFromVoltage-lambdaFromState);
    residual = lambdaFromVoltage-lambdaFromState-offset;
    cycleClosure = zeros(1,3);
    for c = 1:3
        j = c*samplesPerCycle+1;
        cycleClosure(c) = lambdaFromVoltage(j)-lambdaFromVoltage(j-samplesPerCycle) ...
            -(lambdaFromState(j)-lambdaFromState(j-samplesPerCycle));
    end
    fluxTurnBased = lambdaFromState;
    if k==3,turns=74;else,turns=NaN;end
    if isfinite(turns),fluxTurnBased=fluxTurnBased/turns;else,fluxTurnBased(:)=NaN;end
    resultsCell{k} = struct('case_name',cases{k},'data_status','local_Simulink_ideal_circuit', ...
        'time_step_s',dt,'samples',n,'analysis_start_s',tt(1), ...
        'analysis_end_s',tt(end),'L_circuit_H',report.spec.inductance, ...
        'R_circuit_ohm',report.spec.winding_resistance, ...
        'lambda_state_peak_Wb_turn',max(abs(lambdaFromState)), ...
        'lambda_state_peak_to_peak_Wb_turn',max(lambdaFromState)-min(lambdaFromState), ...
        'lambda_reconstruction_rmse_Wb_turn',sqrt(mean(residual.^2)), ...
        'lambda_reconstruction_max_error_Wb_turn',max(abs(residual)), ...
        'lambda_reconstruction_rmse_percent_of_peak', ...
            100*sqrt(mean(residual.^2))/max(abs(lambdaFromState)), ...
        'cycle_closure_error_Wb_turn',cycleClosure, ...
        'integrated_voltage_mean_V',mean(vL), ...
        'state_endpoint_change_Wb_turn',lambdaFromState(end)-lambdaFromState(1), ...
        'turns_only_for_candidate',turns, ...
        'candidate_flux_peak_Wb',max(abs(fluxTurnBased)), ...
        'interpretation','Circuit identity check only; nonlinear core and saturation not solved');
    if k==2
        fig=figure('Visible','off','Color','w','Position',[50 50 1100 700]);
        take=1:n;
        subplot(2,1,1);
        plot(tt(take),lambdaFromState(take)*1e3,'LineWidth',1.1); hold on;
        plot(tt(take),(lambdaFromVoltage(take)-offset)*1e3,'--','LineWidth',0.8);
        ylabel('Flux linkage (mWb turn)'); legend('L i','Integral of v_L, offset aligned','Location','best');
        grid on; title('Linear circuit: final four cycles, 800 steps per switching period');
        subplot(2,1,2);
        plot(tt(take),residual(take)*1e3); grid on;
        ylabel('Residual (mWb turn)'); xlabel('Time (s)');
        title(sprintf('Integral minus L i | RMS / peak linkage = %.3f%% (numerical residual)', ...
            100*sqrt(mean(residual.^2))/max(abs(lambdaFromState))));
        exportgraphics(fig,fullfile(root,'outputs','flux_linkage_check.png'),'Resolution',160);
        close(fig);
    end
end
results = [resultsCell{:}];
fid=fopen(fullfile(root,'outputs','flux_linkage_check.json'),'w','n','UTF-8');
fprintf(fid,'%s',jsonencode(results,PrettyPrint=true)); fclose(fid);
for k=1:numel(results)
    fprintf('%s: RMSE %.4g%% of peak, closure max %.4g Wb-turn\n', ...
        results(k).case_name,results(k).lambda_reconstruction_rmse_percent_of_peak, ...
        max(abs(results(k).cycle_closure_error_Wb_turn)));
end
end
