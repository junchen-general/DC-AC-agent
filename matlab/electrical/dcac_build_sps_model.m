function dcac_build_sps_model(mdl,s,e)
%DCAC_BUILD_SPS_MODEL Four explicit Specialized Power Systems MOSFET circuit.
% Each MOSFET block includes its antiparallel body diode. This is not the
% faster switching-function baseline and requires Simscape Electrical SPS.
load_system('simulink');
load_system('sps_lib');
new_system(mdl);
dt=e.fixed_step_s;
set_param(mdl,'SolverType','Fixed-step','Solver','FixedStepDiscrete', ...
    'FixedStep',num2str(dt,17),'StopTime',num2str(s.stop_time,17), ...
    'ReturnWorkspaceOutputs','on','SaveTime','off','SaveOutput','off');
set_param(mdl,'Description',['Device stage: four explicit Specialized Power Systems ' ...
    'MOSFET blocks with antiparallel body diodes, physical DC source and LC/load network.']);

lossy = contains(e.model_fidelity,'lossy') || contains(e.model_fidelity,'closed_loop');
if lossy
    ron=e.device_rds_on_ohm; vf=e.device_diode_vf_v; rd=e.device_diode_ron_ohm;
else
    ron=1e-5; vf=0; rd=1e-5;
end

add_block('sps_lib/powergui',[mdl '/powergui'],'Position',[25 20 105 55], ...
    'SimulationMode','Discrete','SampleTime',num2str(dt,17), ...
    'frequency',num2str(s.output_frequency,17));
source=add_block('sps_lib/Sources/DC Voltage Source',[mdl '/DC_Source'], ...
    'Position',[70 175 105 235],'Amplitude',num2str(s.input_voltage,17));
idc=add_block('sps_lib/Sensors and Measurements/Current Measurement',[mdl '/DC_Current'], ...
    'Position',[145 115 175 145]);
ground=add_block('sps_lib/Utilities/Ground',[mdl '/DC_Ground'], ...
    'Position',[145 280 170 305]);

mosNames={'Q_A_Upper','Q_A_Lower','Q_B_Upper','Q_B_Lower'};
positions={[250 85 315 130],[250 245 315 290],[400 85 465 130],[400 245 465 290]};
mos=zeros(1,4);
for k=1:4
    mos(k)=add_block('sps_lib/Power Electronics/Mosfet',[mdl '/' mosNames{k}], ...
        'Position',positions{k},'Ron',num2str(ron,17),'Lon','0', ...
        'Rd',num2str(rd,17),'Vfd',num2str(vf,17),'Rs','1e6','Cs','inf', ...
        'Measurements','off');
end

vbridge=add_block('sps_lib/Sensors and Measurements/Voltage Measurement',[mdl '/Bridge_Voltage'], ...
    'Position',[505 155 535 190]);
il=add_block('sps_lib/Sensors and Measurements/Current Measurement',[mdl '/Inductor_Current'], ...
    'Position',[565 105 595 135]);
inductor=add_block('sps_lib/Passives/Series RLC Branch',[mdl '/Filter_L_and_DCR'], ...
    'Position',[630 95 720 145],'BranchType','RL', ...
    'Resistance',num2str(s.winding_resistance,17), ...
    'Inductance',num2str(s.inductance,17));
vout=add_block('sps_lib/Sensors and Measurements/Voltage Measurement',[mdl '/Output_Voltage'], ...
    'Position',[780 155 810 190]);
icap=add_block('sps_lib/Sensors and Measurements/Current Measurement',[mdl '/Capacitor_Current'], ...
    'Position',[805 250 835 280]);
capacitor=add_block('sps_lib/Passives/Series RLC Branch',[mdl '/Filter_C'], ...
    'Position',[865 240 945 290],'BranchType','C', ...
    'Capacitance',num2str(s.capacitance,17));
iload=add_block('sps_lib/Sensors and Measurements/Current Measurement',[mdl '/Load_Current'], ...
    'Position',[805 335 835 365]);

r=s.output_voltage^2/s.output_power;
if strcmp(e.scenario_id,'rated_to_half') || strcmp(e.scenario_id,'load_step')
    baseResistance=r/e.load_ratio_final;
    extraResistance=r/(1-e.load_ratio_final);
    loadBase=add_block('sps_lib/Passives/Series RLC Branch',[mdl '/Half_Load_Base'], ...
        'Position',[945 320 1035 360],'BranchType','R','Resistance',num2str(baseResistance,17));
    breaker=add_block('sps_lib/Power Grid Elements/Breaker',[mdl '/Load_Step_Breaker'], ...
        'Position',[885 390 945 435],'InitialState','1','External','on', ...
        'BreakerResistance',num2str(e.load_breaker_on_resistance_ohm,17), ...
        'SnubberResistance','1e6','SnubberCapacitance','inf');
    loadExtra=add_block('sps_lib/Passives/Series RLC Branch',[mdl '/Half_Load_Switched'], ...
        'Position',[975 390 1065 435],'BranchType','R','Resistance',num2str(extraResistance,17));
    add_block('simulink/Sources/Step',[mdl '/Load_Command'],'Time',num2str(s.load_step_time,17), ...
        'Before','1','After','0','Position',[730 410 780 440]);
    add_line(mdl,'Load_Command/1','Load_Step_Breaker/1','autorouting','on');
else
    loadBase=add_block('sps_lib/Passives/Series RLC Branch',[mdl '/Resistive_Load'], ...
        'Position',[945 330 1035 370],'BranchType','R', ...
        'Resistance',num2str(r/e.load_ratio_initial,17));
    breaker=[]; loadExtra=[];
end

% Physical DC network and two MOSFET legs.
% DC Voltage Source uses LConn=- and RConn=+. The current sensor is oriented
% from source + into the upper-device drains so positive i_dc means input power.
connect(source,'RConn',1,idc,'LConn',1);
connect(idc,'RConn',1,mos(1),'LConn',1);
connect(idc,'RConn',1,mos(3),'LConn',1);
connect(source,'LConn',1,mos(2),'RConn',1);
connect(source,'LConn',1,mos(4),'RConn',1);
connect(source,'LConn',1,ground,'LConn',1);
% Leg A midpoint drives the filter; leg B midpoint is the AC return.
connect(mos(1),'RConn',1,mos(2),'LConn',1);
connect(mos(1),'RConn',1,il,'LConn',1);
connect(mos(1),'RConn',1,vbridge,'LConn',1);
connect(mos(3),'RConn',1,mos(4),'LConn',1);
connect(mos(3),'RConn',1,vbridge,'LConn',2);
connect(il,'RConn',1,inductor,'LConn',1);
connect(inductor,'RConn',1,vout,'LConn',1);
connect(vout,'LConn',2,mos(3),'RConn',1);
% Capacitor branch.
connect(inductor,'RConn',1,icap,'LConn',1);
connect(icap,'RConn',1,capacitor,'LConn',1);
connect(capacitor,'RConn',1,mos(3),'RConn',1);
% Resistive load branch, with an optional switched parallel half-load branch.
connect(inductor,'RConn',1,iload,'LConn',1);
connect(iload,'RConn',1,loadBase,'LConn',1);
connect(loadBase,'RConn',1,mos(3),'RConn',1);
if ~isempty(breaker)
    connect(iload,'RConn',1,breaker,'LConn',1);
    connect(breaker,'RConn',1,loadExtra,'LConn',1);
    connect(loadExtra,'RConn',1,mos(3),'RConn',1);
end

buildGateControl(mdl,s,e);
for k=1:4
    add_line(mdl,sprintf('Gate_Control/%d',k),sprintf('%s/1',mosNames{k}),'autorouting','on');
    ports=get_param(mos(k),'PortHandles');
    if isfield(ports,'Outport') && ~isempty(ports.Outport)
        term=add_block('simulink/Sinks/Terminator',[mdl sprintf('/%s_measurement_unused',mosNames{k})], ...
            'Position',[475 55+55*k 495 75+55*k]);
        termPorts=get_param(term,'PortHandles');
        add_line(mdl,ports.Outport(1),termPorts.Inport(1),'autorouting','on');
    end
end
add_line(mdl,'Output_Voltage/1','Gate_Control/1','autorouting','on');

% Derived electrical signals and legacy-compatible first four columns.
add_block('simulink/Math Operations/Sum',[mdl '/V_L_Terminal'],'Inputs','+-', ...
    'Position',[665 535 700 570]);
add_line(mdl,'Bridge_Voltage/1','V_L_Terminal/1','autorouting','on');
add_line(mdl,'Output_Voltage/1','V_L_Terminal/2','autorouting','on');
add_block('simulink/Math Operations/Gain',[mdl '/V_Winding_R'], ...
    'Gain',num2str(s.winding_resistance,17),'Position',[615 600 690 635]);
add_line(mdl,'Inductor_Current/1','V_Winding_R/1','autorouting','on');
add_block('simulink/Math Operations/Sum',[mdl '/V_Induced'],'Inputs','+-', ...
    'Position',[745 550 780 585]);
add_line(mdl,'V_L_Terminal/1','V_Induced/1','autorouting','on');
add_line(mdl,'V_Winding_R/1','V_Induced/2','autorouting','on');
add_block('simulink/Sources/Step',[mdl '/Load_Conductance'], ...
    'Time',num2str(s.load_step_time,17),'Before',num2str(expectedInitialConductance(r,e),17), ...
    'After',num2str(e.load_ratio_final/r,17),'Position',[830 535 900 570]);
add_block('simulink/Sources/Constant',[mdl '/DC_Voltage_Value'], ...
    'Value',num2str(s.input_voltage,17),'Position',[830 600 900 630]);
add_block('simulink/Signal Routing/Mux',[mdl '/Measurements'], ...
    'Inputs','15','Position',[1100 115 1105 600]);
sources={'Output_Voltage/1','Inductor_Current/1','Load_Current/1','Bridge_Voltage/1', ...
    'V_L_Terminal/1','V_Winding_R/1','V_Induced/1','Capacitor_Current/1', ...
    'Load_Conductance/1','Gate_Control/1','Gate_Control/2','Gate_Control/3','Gate_Control/4', ...
    'DC_Current/1','DC_Voltage_Value/1'};
for k=1:numel(sources), add_line(mdl,sources{k},sprintf('Measurements/%d',k),'autorouting','on'); end
add_block('simulink/Sinks/To Workspace',[mdl '/Recorded_Signals'], ...
    'VariableName','dcac_signals','SaveFormat','Timeseries','MaxDataPoints','inf', ...
    'Position',[1160 235 1310 275]);
add_line(mdl,'Measurements/1','Recorded_Signals/1','autorouting','on');
Simulink.Annotation(mdl,sprintf(['DC/AC Agent | %s\nFour explicit SPS MOSFET devices + body diodes | dead time %.3g us\n' ...
    'Loss parameters are documented in loss_basis_v1.json; total efficiency is not claimed.'], ...
    e.model_fidelity,e.dead_time_s*1e6));
end

function value=expectedInitialConductance(r,e)
if strcmp(e.scenario_id,'rated_to_half') || strcmp(e.scenario_id,'load_step')
    value=e.load_ratio_final/r+1/(r/(1-e.load_ratio_final)+e.load_breaker_on_resistance_ohm);
else
    value=e.load_ratio_initial/r;
end
end

function buildGateControl(mdl,s,e)
p=[mdl '/Gate_Control'];
add_block('simulink/Ports & Subsystems/Subsystem',p,'Position',[120 400 330 520]);
Simulink.SubSystem.deleteContents(p);
add_block('simulink/Ports & Subsystems/In1',[p '/Vout'],'Position',[20 235 50 255]);
add_block('simulink/Sources/Clock',[p '/Time'],'Position',[20 30 50 50]);
add_block('simulink/User-Defined Functions/Fcn',[p '/Carrier'], ...
    'Expr',sprintf('4*abs(u*%.17g-floor(u*%.17g+0.5))-1',s.switching_frequency,s.switching_frequency), ...
    'Position',[90 145 275 180]);
add_line(p,'Time/1','Carrier/1','autorouting','on');
m=e.feedforward_modulation_index;
add_block('simulink/Math Operations/Gain',[p '/Soft_Start_Slope'], ...
    'Gain',num2str(1/e.soft_start_s,17),'Position',[70 195 145 225]);
add_line(p,'Time/1','Soft_Start_Slope/1','autorouting','on');
add_block('simulink/Discontinuities/Saturation',[p '/Soft_Start_Limit'], ...
    'UpperLimit','1','LowerLimit','0','Position',[165 195 225 225]);
add_line(p,'Soft_Start_Slope/1','Soft_Start_Limit/1','autorouting','on');
add_block('simulink/User-Defined Functions/Fcn',[p '/Feedforward_Raw'], ...
    'Expr',sprintf('%.17g*sin(%.17g*u)',m,2*pi*s.output_frequency), ...
    'Position',[90 25 245 55]);
add_line(p,'Time/1','Feedforward_Raw/1','autorouting','on');
add_block('simulink/Math Operations/Product',[p '/Feedforward'], ...
    'Position',[270 25 305 60]);
add_line(p,'Feedforward_Raw/1','Feedforward/1','autorouting','on');
add_line(p,'Soft_Start_Limit/1','Feedforward/2','autorouting','on');
command='Feedforward/1';
if strcmp(e.model_fidelity,'sps_device_closed_loop')
    add_block('simulink/User-Defined Functions/Fcn',[p '/Voltage_Reference_Raw'], ...
        'Expr',sprintf('%.17g*sin(%.17g*u)',sqrt(2)*s.output_voltage, ...
        2*pi*s.output_frequency),'Position',[90 75 245 105]);
    add_line(p,'Time/1','Voltage_Reference_Raw/1','autorouting','on');
    add_block('simulink/Math Operations/Product',[p '/Voltage_Reference'], ...
        'Position',[270 75 305 110]);
    add_line(p,'Voltage_Reference_Raw/1','Voltage_Reference/1','autorouting','on');
    add_line(p,'Soft_Start_Limit/1','Voltage_Reference/2','autorouting','on');
    add_block('simulink/Math Operations/Sum',[p '/Voltage_Error'],'Inputs','+-', ...
        'Position',[315 75 345 110]);
    add_line(p,'Voltage_Reference/1','Voltage_Error/1','autorouting','on');
    add_block('simulink/Discrete/Zero-Order Hold',[p '/Vout_PWM_Sample_Hold'], ...
        'SampleTime',num2str(1/s.switching_frequency,17),'Position',[175 215 285 245]);
    add_line(p,'Vout/1','Vout_PWM_Sample_Hold/1','autorouting','on');
    add_line(p,'Vout_PWM_Sample_Hold/1','Voltage_Error/2','autorouting','on');
    controlTs=1/s.switching_frequency;
    add_block('simulink/Discrete/Zero-Order Hold',[p '/Error_PWM_Sample_Hold'], ...
        'SampleTime',num2str(controlTs,17),'Position',[360 85 420 115]);
    add_line(p,'Voltage_Error/1','Error_PWM_Sample_Hold/1','autorouting','on');
    add_block('simulink/Math Operations/Gain',[p '/P_Action'], ...
        'Gain',num2str(e.controller_kp_per_v,17),'Position',[450 65 515 95]);
    add_line(p,'Error_PWM_Sample_Hold/1','P_Action/1','autorouting','on');
    wc=2*pi*e.controller_bandwidth_hz; w0=2*pi*s.output_frequency;
    bilinearK=2/controlTs;
    numeratorScale=2*e.controller_kr_per_v*wc*bilinearK;
    denominator=[bilinearK^2+2*wc*bilinearK+w0^2, ...
        -2*bilinearK^2+2*w0^2, bilinearK^2-2*wc*bilinearK+w0^2];
    numerator=[numeratorScale 0 -numeratorScale]/denominator(1);
    denominator=denominator/denominator(1);
    add_block('simulink/Discrete/Discrete Transfer Fcn',[p '/Resonant_Action'], ...
        'Numerator',mat2str(numerator,17), ...
        'Denominator',mat2str(denominator,17), ...
        'SampleTime',num2str(controlTs,17),'Position',[450 110 560 145]);
    add_line(p,'Error_PWM_Sample_Hold/1','Resonant_Action/1','autorouting','on');
    add_block('simulink/Math Operations/Sum',[p '/Command_Sum'],'Inputs','+++', ...
        'Position',[590 55 620 115]);
    add_line(p,'Feedforward/1','Command_Sum/1','autorouting','on');
    add_line(p,'P_Action/1','Command_Sum/2','autorouting','on');
    add_line(p,'Resonant_Action/1','Command_Sum/3','autorouting','on');
    add_block('simulink/Discontinuities/Saturation',[p '/Modulation_Limit'], ...
        'UpperLimit',num2str(e.modulation_limit,17),'LowerLimit',num2str(-e.modulation_limit,17), ...
        'Position',[650 70 705 105]);
    add_line(p,'Command_Sum/1','Modulation_Limit/1','autorouting','on');
    command='Modulation_Limit/1';
else
    add_block('simulink/Sinks/Terminator',[p '/Unused_Feedback'],'Position',[90 235 110 255]);
    add_line(p,'Vout/1','Unused_Feedback/1');
end
add_block('simulink/Math Operations/Gain',[p '/Negative_Command'], ...
    'Gain','-1','Position',[700 105 740 135]);
add_line(p,command,'Negative_Command/1','autorouting','on');
for leg=1:2
    cmp=sprintf('Desired_High_%d',leg);
    add_block('simulink/Logic and Bit Operations/Relational Operator',[p '/' cmp], ...
        'Operator','>=','Position',[780 25+100*(leg-1) 830 60+100*(leg-1)]);
    if leg==1, ref=command; else, ref='Negative_Command/1'; end
    add_line(p,ref,[cmp '/1'],'autorouting','on');
    add_line(p,'Carrier/1',[cmp '/2'],'autorouting','on');
    add_block('simulink/Logic and Bit Operations/Logical Operator',[p sprintf('/Desired_Low_%d',leg)], ...
        'Operator','NOT','Position',[860 70+100*(leg-1) 900 100+100*(leg-1)]);
    add_line(p,[cmp '/1'],sprintf('Desired_Low_%d/1',leg),'autorouting','on');
end
desired={'Desired_High_1/1','Desired_Low_1/1','Desired_High_2/1','Desired_Low_2/1'};
names={'Gate_A_Upper','Gate_A_Lower','Gate_B_Upper','Gate_B_Lower'};
for k=1:4
    add_block('simulink/Signal Attributes/Data Type Conversion',[p sprintf('/Desired_Double_%d',k)], ...
        'OutDataTypeStr','double','Position',[915 15+55*(k-1) 965 45+55*(k-1)]);
    add_line(p,desired{k},sprintf('Desired_Double_%d/1',k),'autorouting','on');
    add_block('simulink/Continuous/Transport Delay',[p sprintf('/On_Delay_%d',k)], ...
        'DelayTime',num2str(e.dead_time_s,17),'Position',[985 15+55*(k-1) 1055 45+55*(k-1)]);
    add_line(p,sprintf('Desired_Double_%d/1',k),sprintf('On_Delay_%d/1',k),'autorouting','on');
    add_block('simulink/Signal Attributes/Data Type Conversion',[p sprintf('/Delayed_Boolean_%d',k)], ...
        'OutDataTypeStr','boolean','Position',[1070 15+55*(k-1) 1130 45+55*(k-1)]);
    add_line(p,sprintf('On_Delay_%d/1',k),sprintf('Delayed_Boolean_%d/1',k),'autorouting','on');
    add_block('simulink/Logic and Bit Operations/Logical Operator',[p sprintf('/Interlock_%d',k)], ...
        'Operator','AND','Inputs','2','Position',[1150 10+55*(k-1) 1195 50+55*(k-1)]);
    add_line(p,desired{k},sprintf('Interlock_%d/1',k),'autorouting','on');
    add_line(p,sprintf('Delayed_Boolean_%d/1',k),sprintf('Interlock_%d/2',k),'autorouting','on');
    add_block('simulink/Signal Attributes/Data Type Conversion',[p sprintf('/Double_%d',k)], ...
        'OutDataTypeStr','double','Position',[1210 15+55*(k-1) 1275 45+55*(k-1)]);
    add_line(p,sprintf('Interlock_%d/1',k),sprintf('Double_%d/1',k),'autorouting','on');
    add_block('simulink/Ports & Subsystems/Out1',[p '/' names{k}], ...
        'Port',num2str(k),'Position',[1300 20+55*(k-1) 1330 40+55*(k-1)]);
    add_line(p,sprintf('Double_%d/1',k),[names{k} '/1'],'autorouting','on');
end
end

function connect(blockA,sideA,indexA,blockB,sideB,indexB)
model=bdroot(blockA);
portsA=get_param(blockA,'PortHandles'); portsB=get_param(blockB,'PortHandles');
add_line(model,portsA.(sideA)(indexA),portsB.(sideB)(indexB),'autorouting','on');
end
