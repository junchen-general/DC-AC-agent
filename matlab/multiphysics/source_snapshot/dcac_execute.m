function dcac_execute(requestPath)
% DCAC_EXECUTE Build and optionally simulate a real, editable Simulink model.
% Fidelity: ideal full-bridge switching functions + continuous LC equations.
% No semiconductor loss, dead time, magnetic/thermal/structural FEA yet.
request = jsondecode(fileread(requestPath));
outdir = char(request.output_dir);
if ~isfolder(outdir), mkdir(outdir); end
resultPath = fullfile(outdir, 'result.json');
try
    s = request.spec;
    mdl = 'dcac_inverter';
    if bdIsLoaded(mdl), close_system(mdl, 0); end
    load_system('simulink');
    new_system(mdl);
    cleanup = onCleanup(@() closeIfLoaded(mdl)); %#ok<NASGU>
    dt = 1/(s.switching_frequency*100);
    set_param(mdl, 'SolverType','Fixed-step', 'Solver','ode4', ...
        'FixedStep',num2str(dt,17), 'StopTime',num2str(s.stop_time,17), ...
        'ReturnWorkspaceOutputs','on', 'SaveTime','off', 'SaveOutput','off');
    set_param(mdl, 'Description', ['DC/AC Agent v0.1: ideal unipolar SPWM full-bridge ' ...
        'switching-function model; LC state equations; open loop; SI units. ' ...
        'No semiconductor loss, dead time or multiphysics FEA.']);
    buildPWM(mdl, s);
    buildBridge(mdl, s);
    buildFilter(mdl, s);
    add_line(mdl,'SPWM/1','Full_Bridge/1','autorouting','on');
    add_line(mdl,'SPWM/2','Full_Bridge/2','autorouting','on');
    add_line(mdl,'Full_Bridge/1','LC_Filter/1','autorouting','on');
    add_block('simulink/Signal Routing/Mux',[mdl '/Measurements'], ...
        'Inputs','4','Position',[790 110 795 240]);
    add_line(mdl,'LC_Filter/1','Measurements/1','autorouting','on');
    add_line(mdl,'LC_Filter/2','Measurements/2','autorouting','on');
    add_line(mdl,'LC_Filter/3','Measurements/3','autorouting','on');
    add_line(mdl,'Full_Bridge/1','Measurements/4','autorouting','on');
    add_block('simulink/Sinks/To Workspace',[mdl '/Recorded_Signals'], ...
        'VariableName','dcac_signals','SaveFormat','Timeseries', ...
        'MaxDataPoints','inf','Position',[865 140 1015 180]);
    add_line(mdl,'Measurements/1','Recorded_Signals/1','autorouting','on');
    add_block('simulink/Sinks/Scope',[mdl '/Output_Scope'], ...
        'Position',[870 215 930 260]);
    add_line(mdl,'Measurements/1','Output_Scope/1','autorouting','on');
    Simulink.Annotation(mdl, sprintf(['DC/AC Agent | ideal full-bridge + LC | OPEN LOOP\n' ...
        'Vin %.0f V | Vout target %.0f Vrms | %.0f W | %.0f Hz | fsw %.0f kHz\n' ...
        'Measurements: Vout [V], IL [A], Iload [A], Vbridge [V]\n' ...
        'No device-level losses / dead time / magnetic, thermal or structural FEA'], ...
        s.input_voltage,s.output_voltage,s.output_power,s.output_frequency,s.switching_frequency/1000));
    set_param(mdl,'SimulationCommand','update');
    modelPath = fullfile(outdir,[mdl '.slx']);
    save_system(mdl,modelPath);
    result = struct('ok',true,'action',request.action,'source','MATLAB/Simulink', ...
        'matlab_version',version,'model_level','ideal_switching_function_open_loop', ...
        'model_path',modelPath,'spec',s);
    if strcmp(request.action,'simulate')
        simulation = sim(mdl);
        ts = simulation.get('dcac_signals');
        t = ts.Time(:); y = squeeze(ts.Data);
        if size(y,1) ~= numel(t), y = y.'; end
        save(fullfile(outdir,'simulation.mat'),'t','y','s','-v7');
        writematrix([t y],fullfile(outdir,'signals.csv'));
        % Last exactly four fundamental cycles; exclude the right endpoint.
        n = round(4/s.output_frequency/dt);
        segment = y(end-n:end-1,:);
        v = segment(:,1); il = segment(:,2); io = segment(:,3);
        rmsV = sqrt(mean(v.^2));
        amps = 2*abs(fft(v))/numel(v);
        bin = 4; fundamental = amps(bin+1);
        harmonicNumbers = (1:40).';
        harmonicAmps = amps(harmonicNumbers*bin+1);
        thd = 100*sqrt(sum(harmonicAmps(2:end).^2))/max(fundamental,eps);
        if any(~isfinite(y(:))) || ~isfinite(thd), error('DCAC:Invalid','Simulation contains nonfinite results.'); end
        metrics = struct('output_rms',rmsV, 'current_rms',sqrt(mean(io.^2)), ...
            'inductor_rms',sqrt(mean(il.^2)), 'inductor_peak',max(abs(il)), ...
            'output_power',mean(v.*io), 'winding_loss',mean(il.^2)*s.winding_resistance, ...
            'thd_percent',thd,'voltage_error_percent',100*(rmsV/s.output_voltage-1), ...
            'analysis_cycles',4,'harmonic_max',40,'sample_time',dt, ...
            'analysis_start',t(end-n),'analysis_end',t(end-1));
        result.metrics = metrics;
        result.checks = struct('voltage',abs(metrics.voltage_error_percent)<=5,'thd',thd<5);
        idx = unique(round(linspace(1,numel(t),min(3200,numel(t)))));
        result.waveforms = struct('time',t(idx).','voltage',y(idx,1).', ...
            'inductor_current',y(idx,2).','load_current',y(idx,3).');
        result.harmonics = struct('order',harmonicNumbers.','amplitude',harmonicAmps.');
        result.analysis_notes = { ...
            'Actual Simulink ode4 fixed-step simulation; not synthetic demo data.', ...
            'Open-loop ideal full-bridge switching-function model with 40 ms soft start.', ...
            'THD uses harmonics 2 through 40 over the final four whole cycles; excludes carrier-band content.', ...
            'Only specified inductor resistance loss is evaluated; total efficiency is not evaluated.', ...
            'Magnetic/thermal/structural FEA is not implemented in this release.'};
        try
            f = figure('Visible','off','Color','w','Position',[100 100 1100 700]);
            tiledlayout(2,1);
            nexttile; plot(t(idx),y(idx,1),'Color',[0.12 0.5 0.4]); grid on;
            ylabel('Output voltage (V)'); xlabel('Time (s)');
            title(sprintf('DC/AC Agent | %.2f Vrms | THD(2-40) %.3f%%',rmsV,thd));
            nexttile; plot(t(idx),y(idx,2),'Color',[0.15 0.35 0.65]); grid on;
            ylabel('Inductor current (A)'); xlabel('Time (s)');
            exportgraphics(f,fullfile(outdir,'waveforms.png'),'Resolution',160); close(f);
        catch plotError
            result.plot_warning = plotError.message;
        end
    end
    writeJSON(resultPath,result);
    fprintf('DCAC_SUCCESS %s\n',resultPath);
catch err
    result = struct('ok',false,'error',err.message,'identifier',err.identifier, ...
        'report',getReport(err,'extended','hyperlinks','off'));
    writeJSON(resultPath,result);
    fprintf(2,'%s\n',result.report);
    rethrow(err);
end
end

function buildPWM(mdl,s)
p = [mdl '/SPWM'];
add_block('simulink/Ports & Subsystems/Subsystem',p,'Position',[80 125 245 245],'BackgroundColor','lightBlue');
Simulink.SubSystem.deleteContents(p);
add_block('simulink/Sources/Clock',[p '/Time'],'Position',[30 80 60 100]);
add_block('simulink/User-Defined Functions/Fcn',[p '/Triangular_Carrier'], ...
    'Expr',sprintf('4*abs(u*%.17g-floor(u*%.17g+0.5))-1',s.switching_frequency,s.switching_frequency), ...
    'Position',[110 200 300 235]);
add_line(p,'Time/1','Triangular_Carrier/1','autorouting','on');
m = sqrt(2)*s.output_voltage/s.input_voltage;
add_block('simulink/User-Defined Functions/Fcn',[p '/Sine_Reference'], ...
    'Expr',sprintf('%.17g*sin(%.17g*u)*min(u/0.04,1)',m,2*pi*s.output_frequency), ...
    'Position',[110 50 300 90]);
add_line(p,'Time/1','Sine_Reference/1','autorouting','on');
add_block('simulink/Math Operations/Gain',[p '/Negative_Reference'], ...
    'Gain','-1','Position',[340 110 380 140]);
add_line(p,'Sine_Reference/1','Negative_Reference/1','autorouting','on');
for k = 1:2
    name = sprintf('Compare_%d',k);
    add_block('simulink/Logic and Bit Operations/Relational Operator',[p '/' name], ...
        'Operator','>=','Position',[430 40+100*(k-1) 480 80+100*(k-1)]);
    if k==1, reference='Sine_Reference/1'; else, reference='Negative_Reference/1'; end
    add_line(p,reference,[name '/1'],'autorouting','on');
    add_line(p,'Triangular_Carrier/1',[name '/2'],'autorouting','on');
    add_block('simulink/Signal Attributes/Data Type Conversion',[p sprintf('/Double_%d',k)], ...
        'OutDataTypeStr','double','Position',[520 45+100*(k-1) 590 75+100*(k-1)]);
    add_line(p,[name '/1'],sprintf('Double_%d/1',k),'autorouting','on');
    add_block('simulink/Ports & Subsystems/Out1',[p sprintf('/Gate_%d',k)], ...
        'Port',num2str(k),'Position',[650 50+100*(k-1) 680 70+100*(k-1)]);
    add_line(p,sprintf('Double_%d/1',k),sprintf('Gate_%d/1',k),'autorouting','on');
end
end

function buildBridge(mdl,s)
p = [mdl '/Full_Bridge'];
add_block('simulink/Ports & Subsystems/Subsystem',p,'Position',[325 125 485 245],'BackgroundColor','lightOrange');
Simulink.SubSystem.deleteContents(p);
for k = 1:2
    add_block('simulink/Ports & Subsystems/In1',[p sprintf('/Gate_%d',k)], ...
        'Port',num2str(k),'Position',[40 50+80*(k-1) 70 70+80*(k-1)]);
    add_block('simulink/Math Operations/Sum',[p sprintf('/Lower_Gate_%d',k)], ...
        'Inputs','+-','Position',[140 200+70*(k-1) 165 225+70*(k-1)]);
end
add_block('simulink/Sources/Constant',[p '/One'],'Value','1','Position',[40 220 75 245]);
for k = 1:2
    add_line(p,'One/1',sprintf('Lower_Gate_%d/1',k),'autorouting','on');
    add_line(p,sprintf('Gate_%d/1',k),sprintf('Lower_Gate_%d/2',k),'autorouting','on');
    add_block('simulink/Sinks/Terminator',[p sprintf('/Complementary_%d',k)], ...
        'Position',[230 200+70*(k-1) 250 220+70*(k-1)]);
    add_line(p,sprintf('Lower_Gate_%d/1',k),sprintf('Complementary_%d/1',k));
end
add_block('simulink/Math Operations/Sum',[p '/Leg_Difference'],'Inputs','+-','Position',[160 70 190 110]);
add_line(p,'Gate_1/1','Leg_Difference/1','autorouting','on');
add_line(p,'Gate_2/1','Leg_Difference/2','autorouting','on');
add_block('simulink/Math Operations/Gain',[p '/DC_Link'],'Gain',num2str(s.input_voltage,17),'Position',[250 70 330 110]);
add_line(p,'Leg_Difference/1','DC_Link/1');
add_block('simulink/Ports & Subsystems/Out1',[p '/Bridge_Voltage'],'Position',[390 80 420 100]);
add_line(p,'DC_Link/1','Bridge_Voltage/1');
Simulink.Annotation(p,'Ideal full bridge: Vab = Vin*(Sa-Sb). Lower gates are complementary. No dead time/device losses.');
end

function buildFilter(mdl,s)
p = [mdl '/LC_Filter'];
add_block('simulink/Ports & Subsystems/Subsystem',p,'Position',[565 125 725 245],'BackgroundColor','lightGreen');
Simulink.SubSystem.deleteContents(p);
add_block('simulink/Ports & Subsystems/In1',[p '/Bridge_Voltage'],'Position',[25 60 55 80]);
add_block('simulink/Math Operations/Sum',[p '/Inductor_Voltage'],'Inputs','+--','Position',[140 50 170 105]);
add_block('simulink/Math Operations/Gain',[p '/Inv_L'],'Gain',num2str(1/s.inductance,17),'Position',[215 60 280 95]);
add_block('simulink/Continuous/Integrator',[p '/Inductor_Current'],'Position',[325 60 360 95]);
add_block('simulink/Math Operations/Gain',[p '/Winding_R'],'Gain',num2str(s.winding_resistance,17),'Position',[290 160 360 195]);
add_line(p,'Bridge_Voltage/1','Inductor_Voltage/1','autorouting','on');
add_line(p,'Inductor_Voltage/1','Inv_L/1'); add_line(p,'Inv_L/1','Inductor_Current/1');
add_line(p,'Inductor_Current/1','Winding_R/1','autorouting','on');
add_line(p,'Winding_R/1','Inductor_Voltage/2','autorouting','on');
add_block('simulink/Math Operations/Sum',[p '/Capacitor_Current'],'Inputs','+-','Position',[420 60 450 100]);
add_block('simulink/Math Operations/Gain',[p '/Inv_C'],'Gain',num2str(1/s.capacitance,17),'Position',[490 60 550 95]);
add_block('simulink/Continuous/Integrator',[p '/Output_Voltage'],'Position',[590 60 625 95]);
add_line(p,'Inductor_Current/1','Capacitor_Current/1','autorouting','on');
add_line(p,'Capacitor_Current/1','Inv_C/1'); add_line(p,'Inv_C/1','Output_Voltage/1');
add_line(p,'Output_Voltage/1','Inductor_Voltage/3','autorouting','on');
r = s.output_voltage^2/s.output_power;
add_block('simulink/Sources/Step',[p '/Load_Conductance'], ...
    'Time',num2str(s.load_step_time,17),'Before',num2str(1/r,17), ...
    'After',num2str((1 + double(s.load_step)*(s.load_final_ratio-1))/r,17), ...
    'Position',[380 260 440 300]);
add_block('simulink/Math Operations/Product',[p '/Load_Current'],'Position',[590 200 630 240]);
add_line(p,'Output_Voltage/1','Load_Current/1','autorouting','on');
add_line(p,'Load_Conductance/1','Load_Current/2','autorouting','on');
add_line(p,'Load_Current/1','Capacitor_Current/2','autorouting','on');
names = {'Vout','IL','Iload'}; sources={'Output_Voltage/1','Inductor_Current/1','Load_Current/1'};
for k=1:3
    add_block('simulink/Ports & Subsystems/Out1',[p '/' names{k}], ...
        'Port',num2str(k),'Position',[760 40+80*k 790 60+80*k]);
    add_line(p,sources{k},[names{k} '/1'],'autorouting','on');
end
Simulink.Annotation(p,'L*dIL/dt = Vab - rL*IL - Vout; C*dVout/dt = IL - Gload(t)*Vout');
end

function writeJSON(path,data)
fid = fopen(path,'w','n','UTF-8');
if fid<0, error('DCAC:IO','Cannot write result JSON'); end
cleanup=onCleanup(@() fclose(fid)); %#ok<NASGU>
fprintf(fid,'%s',jsonencode(data));
end

function closeIfLoaded(mdl)
if bdIsLoaded(mdl), close_system(mdl,0); end
end
