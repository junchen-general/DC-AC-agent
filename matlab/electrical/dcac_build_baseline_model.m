function dcac_build_baseline_model(mdl,s,e)
%DCAC_BUILD_BASELINE_MODEL Fast switching-function reference model.
load_system('simulink');
new_system(mdl);
dt = e.fixed_step_s;
set_param(mdl,'SolverType','Fixed-step','Solver','ode4', ...
    'FixedStep',num2str(dt,17),'StopTime',num2str(s.stop_time,17), ...
    'ReturnWorkspaceOutputs','on','SaveTime','off','SaveOutput','off');
set_param(mdl,'Description',['Stage 0 baseline: ideal unipolar SPWM switching function ' ...
    'plus continuous LC state equations. Open loop. No dead time or device loss.']);
buildPWM(mdl,s,e);
buildBridge(mdl,s);
buildFilter(mdl,s,e);
add_line(mdl,'SPWM/1','Full_Bridge/1','autorouting','on');
add_line(mdl,'SPWM/3','Full_Bridge/2','autorouting','on');
add_line(mdl,'Full_Bridge/1','LC_Filter/1','autorouting','on');

add_block('simulink/Math Operations/Product',[mdl '/Ideal_DC_Power'], ...
    'Position',[745 320 780 355]);
add_line(mdl,'Full_Bridge/1','Ideal_DC_Power/1','autorouting','on');
add_line(mdl,'LC_Filter/2','Ideal_DC_Power/2','autorouting','on');
add_block('simulink/Math Operations/Gain',[mdl '/Ideal_DC_Current'], ...
    'Gain',num2str(1/s.input_voltage,17),'Position',[810 320 880 355]);
add_line(mdl,'Ideal_DC_Power/1','Ideal_DC_Current/1','autorouting','on');
add_block('simulink/Sources/Constant',[mdl '/DC_Voltage_Value'], ...
    'Value',num2str(s.input_voltage,17),'Position',[805 375 875 405]);
add_block('simulink/Signal Routing/Mux',[mdl '/Measurements'], ...
    'Inputs','15','Position',[930 75 935 455]);
for k=1:3, add_line(mdl,sprintf('LC_Filter/%d',k),sprintf('Measurements/%d',k),'autorouting','on'); end
add_line(mdl,'Full_Bridge/1','Measurements/4','autorouting','on');
for k=4:8, add_line(mdl,sprintf('LC_Filter/%d',k),sprintf('Measurements/%d',k+1),'autorouting','on'); end
for k=1:4, add_line(mdl,sprintf('SPWM/%d',k),sprintf('Measurements/%d',k+9),'autorouting','on'); end
add_line(mdl,'Ideal_DC_Current/1','Measurements/14','autorouting','on');
add_line(mdl,'DC_Voltage_Value/1','Measurements/15','autorouting','on');
add_block('simulink/Sinks/To Workspace',[mdl '/Recorded_Signals'], ...
    'VariableName','dcac_signals','SaveFormat','Timeseries','MaxDataPoints','inf', ...
    'Position',[990 155 1140 195]);
add_line(mdl,'Measurements/1','Recorded_Signals/1','autorouting','on');
add_block('simulink/Sinks/Scope',[mdl '/Output_Scope'],'Position',[1005 235 1065 280]);
add_line(mdl,'Measurements/1','Output_Scope/1','autorouting','on');
Simulink.Annotation(mdl,sprintf(['DC/AC Agent | Stage 0 baseline | OPEN LOOP\n' ...
    'Vin %.0f V | Vout %.0f Vrms | %.0f W | %.0f Hz | fsw %.0f kHz\n' ...
    'Ideal switching function + LC state equations; no dead time/device loss'], ...
    s.input_voltage,s.output_voltage,s.output_power,s.output_frequency,s.switching_frequency/1000));
end

function buildPWM(mdl,s,e)
p = [mdl '/SPWM'];
add_block('simulink/Ports & Subsystems/Subsystem',p,'Position',[65 105 255 265]);
Simulink.SubSystem.deleteContents(p);
add_block('simulink/Sources/Clock',[p '/Time'],'Position',[25 80 55 100]);
add_block('simulink/User-Defined Functions/Fcn',[p '/Triangular_Carrier'], ...
    'Expr',sprintf('4*abs(u*%.17g-floor(u*%.17g+0.5))-1',s.switching_frequency,s.switching_frequency), ...
    'Position',[95 195 285 230]);
add_line(p,'Time/1','Triangular_Carrier/1','autorouting','on');
m = sqrt(2)*s.output_voltage/s.input_voltage;
add_block('simulink/User-Defined Functions/Fcn',[p '/Sine_Raw'], ...
    'Expr',sprintf('%.17g*sin(%.17g*u)',m,2*pi*s.output_frequency), ...
    'Position',[95 25 255 55]);
add_line(p,'Time/1','Sine_Raw/1','autorouting','on');
add_block('simulink/Math Operations/Gain',[p '/Soft_Start_Slope'], ...
    'Gain',num2str(1/e.soft_start_s,17),'Position',[95 75 175 105]);
add_line(p,'Time/1','Soft_Start_Slope/1','autorouting','on');
add_block('simulink/Discontinuities/Saturation',[p '/Soft_Start_Limit'], ...
    'UpperLimit','1','LowerLimit','0','Position',[205 75 265 105]);
add_line(p,'Soft_Start_Slope/1','Soft_Start_Limit/1','autorouting','on');
add_block('simulink/Math Operations/Product',[p '/Sine_Reference'], ...
    'Position',[300 30 340 65]);
add_line(p,'Sine_Raw/1','Sine_Reference/1','autorouting','on');
add_line(p,'Soft_Start_Limit/1','Sine_Reference/2','autorouting','on');
add_block('simulink/Math Operations/Gain',[p '/Negative_Reference'], ...
    'Gain','-1','Position',[365 95 405 125]);
add_line(p,'Sine_Reference/1','Negative_Reference/1','autorouting','on');
for k=1:2
    name=sprintf('Compare_%d',k);
    add_block('simulink/Logic and Bit Operations/Relational Operator',[p '/' name], ...
        'Operator','>=','Position',[450 35+100*(k-1) 500 70+100*(k-1)]);
    if k==1, reference='Sine_Reference/1'; else, reference='Negative_Reference/1'; end
    add_line(p,reference,[name '/1'],'autorouting','on');
    add_line(p,'Triangular_Carrier/1',[name '/2'],'autorouting','on');
    add_block('simulink/Logic and Bit Operations/Logical Operator',[p sprintf('/Not_%d',k)], ...
        'Operator','NOT','Position',[530 105+100*(k-1) 570 135+100*(k-1)]);
    add_line(p,[name '/1'],sprintf('Not_%d/1',k),'autorouting','on');
end
sources={'Compare_1/1','Not_1/1','Compare_2/1','Not_2/1'};
names={'Gate_A_Upper','Gate_A_Lower','Gate_B_Upper','Gate_B_Lower'};
for k=1:4
    add_block('simulink/Signal Attributes/Data Type Conversion',[p sprintf('/Double_%d',k)], ...
        'OutDataTypeStr','double','Position',[600 25+48*(k-1) 665 50+48*(k-1)]);
    add_line(p,sources{k},sprintf('Double_%d/1',k),'autorouting','on');
    add_block('simulink/Ports & Subsystems/Out1',[p '/' names{k}], ...
        'Port',num2str(k),'Position',[720 28+48*(k-1) 750 48+48*(k-1)]);
    add_line(p,sprintf('Double_%d/1',k),[names{k} '/1'],'autorouting','on');
end
end

function buildBridge(mdl,s)
p=[mdl '/Full_Bridge'];
add_block('simulink/Ports & Subsystems/Subsystem',p,'Position',[330 120 495 245]);
Simulink.SubSystem.deleteContents(p);
for k=1:2
    add_block('simulink/Ports & Subsystems/In1',[p sprintf('/Upper_Gate_%d',k)], ...
        'Port',num2str(k),'Position',[35 45+70*(k-1) 65 65+70*(k-1)]);
end
add_block('simulink/Math Operations/Sum',[p '/Leg_Difference'],'Inputs','+-', ...
    'Position',[145 65 175 105]);
add_line(p,'Upper_Gate_1/1','Leg_Difference/1','autorouting','on');
add_line(p,'Upper_Gate_2/1','Leg_Difference/2','autorouting','on');
add_block('simulink/Math Operations/Gain',[p '/DC_Link'], ...
    'Gain',num2str(s.input_voltage,17),'Position',[230 65 310 105]);
add_line(p,'Leg_Difference/1','DC_Link/1');
add_block('simulink/Ports & Subsystems/Out1',[p '/Bridge_Voltage'], ...
    'Position',[370 75 400 95]);
add_line(p,'DC_Link/1','Bridge_Voltage/1');
Simulink.Annotation(p,['Ideal reference only: Vab=Vin*(Sa-Sb). ' ...
    'Complementary gates are logged but the semiconductor commutation path is not solved.']);
end

function buildFilter(mdl,s,e)
p=[mdl '/LC_Filter'];
add_block('simulink/Ports & Subsystems/Subsystem',p,'Position',[565 95 745 285]);
Simulink.SubSystem.deleteContents(p);
add_block('simulink/Ports & Subsystems/In1',[p '/Bridge_Voltage'], ...
    'Position',[20 45 50 65]);
add_block('simulink/Math Operations/Sum',[p '/Inductor_Voltage'], ...
    'Inputs','+--','Position',[125 35 155 90]);
add_block('simulink/Math Operations/Gain',[p '/Inv_L'], ...
    'Gain',num2str(1/s.inductance,17),'Position',[195 45 260 80]);
add_block('simulink/Continuous/Integrator',[p '/Inductor_Current'], ...
    'Position',[300 45 335 80]);
add_block('simulink/Math Operations/Gain',[p '/Winding_R'], ...
    'Gain',num2str(s.winding_resistance,17),'Position',[275 135 350 170]);
add_line(p,'Bridge_Voltage/1','Inductor_Voltage/1','autorouting','on');
add_line(p,'Inductor_Voltage/1','Inv_L/1');
add_line(p,'Inv_L/1','Inductor_Current/1');
add_line(p,'Inductor_Current/1','Winding_R/1','autorouting','on');
add_line(p,'Winding_R/1','Inductor_Voltage/2','autorouting','on');
add_block('simulink/Math Operations/Sum',[p '/Capacitor_Current'], ...
    'Inputs','+-','Position',[400 35 430 75]);
add_block('simulink/Math Operations/Gain',[p '/Inv_C'], ...
    'Gain',num2str(1/s.capacitance,17),'Position',[470 40 530 75]);
add_block('simulink/Continuous/Integrator',[p '/Output_Voltage'], ...
    'Position',[565 40 600 75]);
add_line(p,'Inductor_Current/1','Capacitor_Current/1','autorouting','on');
add_line(p,'Capacitor_Current/1','Inv_C/1');
add_line(p,'Inv_C/1','Output_Voltage/1');
add_line(p,'Output_Voltage/1','Inductor_Voltage/3','autorouting','on');
r=s.output_voltage^2/s.output_power;
add_block('simulink/Sources/Step',[p '/Load_Conductance'], ...
    'Time',num2str(s.load_step_time,17), ...
    'Before',num2str(e.load_ratio_initial/r,17), ...
    'After',num2str(e.load_ratio_final/r,17), ...
    'Position',[360 240 430 275]);
add_block('simulink/Math Operations/Product',[p '/Load_Current'], ...
    'Position',[565 185 605 225]);
add_line(p,'Output_Voltage/1','Load_Current/1','autorouting','on');
add_line(p,'Load_Conductance/1','Load_Current/2','autorouting','on');
add_line(p,'Load_Current/1','Capacitor_Current/2','autorouting','on');
add_block('simulink/Math Operations/Sum',[p '/Terminal_Voltage'], ...
    'Inputs','+-','Position',[400 105 430 140]);
add_line(p,'Bridge_Voltage/1','Terminal_Voltage/1','autorouting','on');
add_line(p,'Output_Voltage/1','Terminal_Voltage/2','autorouting','on');
names={'Vout','IL','Iload','V_L_terminal','V_R_winding','V_induced','I_capacitor','Load_G'};
sources={'Output_Voltage/1','Inductor_Current/1','Load_Current/1','Terminal_Voltage/1', ...
    'Winding_R/1','Inductor_Voltage/1','Capacitor_Current/1','Load_Conductance/1'};
for k=1:numel(names)
    add_block('simulink/Ports & Subsystems/Out1',[p '/' names{k}], ...
        'Port',num2str(k),'Position',[710 20+32*k 740 40+32*k]);
    add_line(p,sources{k},[names{k} '/1'],'autorouting','on');
end
Simulink.Annotation(p,['L*dIL/dt=Vbridge-rL*IL-Vout; C*dVout/dt=IL-Gload*Vout. ' ...
    'All exported voltages use bridge-to-load current sign convention.']);
end
