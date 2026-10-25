function [s,e,context] = dcac_normalize_request(request)
%DCAC_NORMALIZE_REQUEST Validate the additive electrical request namespace.
s = request.spec;
required = {'input_voltage','output_voltage','output_power','output_frequency', ...
    'switching_frequency','inductance','capacitance','winding_resistance', ...
    'stop_time','load_step','load_step_time','load_final_ratio'};
for k = 1:numel(required)
    if ~isfield(s,required{k})
        error('DCAC:Request','Missing spec field: %s',required{k});
    end
end
positiveSpec={'input_voltage','output_voltage','output_power','output_frequency', ...
    'switching_frequency','inductance','capacitance','stop_time'};
for k=1:numel(positiveSpec), requirePositiveScalar(s.(positiveSpec{k}),['spec.' positiveSpec{k}]); end
requireNonnegativeScalar(s.winding_resistance,'spec.winding_resistance');
requireNonnegativeScalar(s.load_step_time,'spec.load_step_time');
requirePositiveScalar(s.load_final_ratio,'spec.load_final_ratio');
if ~islogical(s.load_step) || ~isscalar(s.load_step)
    error('DCAC:Request','spec.load_step must be a logical scalar.');
end
if s.load_final_ratio>1
    error('DCAC:Request','spec.load_final_ratio must not exceed 1 for this passive load-step template.');
end

e = struct;
if isfield(request,'electrical'), e = request.electrical; end
suppliedDeviceFields=intersect(fieldnames(e),{'device_part','device_rds_on_ohm', ...
    'device_diode_vf_v','device_diode_ron_ohm','device_rise_time_s','device_fall_time_s', ...
    'device_reverse_recovery_charge_c'});
e = setDefault(e,'schema_version','dcac.electrical.request/1.0');
e = setDefault(e,'model_fidelity','baseline_ideal_switching_open_loop');
e = setDefault(e,'scenario_id',scenarioFromLegacy(s));
e = setDefault(e,'steps_per_switching_period',100);
e = setDefault(e,'dead_time_s',1e-6);
e = setDefault(e,'soft_start_s',0.04);
e = setDefault(e,'controller_kp_per_v',1.5e-3);
e = setDefault(e,'controller_kr_per_v',1.0e-2);
e = setDefault(e,'controller_bandwidth_hz',5);
e = setDefault(e,'modulation_limit',0.95);
% Keep legacy/direct requests unchanged unless the additive option is selected.
% Validation enables this for the closed-loop design.  The compensation is
% the fundamental component of the measured full-bridge dead-time voltage
% error, Delta m = 8*f_sw*t_dead/pi.
e = setDefault(e,'closed_loop_dead_time_compensation',false);
e = setDefault(e,'device_part','IPW65R041CFD7');
e = setDefault(e,'device_rds_on_ohm',0.076);
e = setDefault(e,'device_diode_vf_v',1.0);
e = setDefault(e,'device_diode_ron_ohm',1e-3);
e = setDefault(e,'device_rise_time_s',12e-9);
e = setDefault(e,'device_fall_time_s',3e-9);
e = setDefault(e,'device_reverse_recovery_charge_c',1.2e-6);
e = setDefault(e,'device_junction_temperature_c',150);
e = setDefault(e,'load_breaker_on_resistance_ohm',0.01);
e = setDefault(e,'export_full_csv',true);
e = setDefault(e,'export_legacy_csv',true);
e = setDefault(e,'export_legacy_mat',true);
if isempty(suppliedDeviceFields)
    e.device_parameter_source_status='manufacturer_datasheet_defaults';
elseif isfield(e,'device_source') && isstruct(e.device_source) && ~isempty(e.device_source)
    e.device_parameter_source_status='user_supplied_with_source';
else
    e.device_parameter_source_status='user_supplied_unverified';
end

allowedFidelity = {'baseline_ideal_switching_open_loop', ...
    'sps_device_open_loop','sps_device_lossy_open_loop','sps_device_closed_loop'};
if ~any(strcmp(e.model_fidelity,allowedFidelity))
    error('DCAC:Request','Unsupported model_fidelity: %s',e.model_fidelity);
end
allowedScenario = {'rated','half_load','rated_to_half','load_step'};
if ~any(strcmp(e.scenario_id,allowedScenario))
    error('DCAC:Request','Unsupported scenario_id: %s',e.scenario_id);
end
if ~isnumeric(e.steps_per_switching_period) || ~isscalar(e.steps_per_switching_period) || ...
        ~isfinite(e.steps_per_switching_period) || ...
        e.steps_per_switching_period < 20 || e.steps_per_switching_period > 1000 || ...
        fix(e.steps_per_switching_period) ~= e.steps_per_switching_period
    error('DCAC:Request','steps_per_switching_period must be an integer from 20 to 1000.');
end
if ~isnumeric(e.dead_time_s) || ~isscalar(e.dead_time_s) || ~isfinite(e.dead_time_s) || e.dead_time_s < 0 || ...
        e.dead_time_s >= 0.25/s.switching_frequency
    error('DCAC:Request','dead_time_s must be nonnegative and below one quarter switching period.');
end
if ~isnumeric(e.modulation_limit) || ~isscalar(e.modulation_limit) || ...
        ~isfinite(e.modulation_limit) || e.modulation_limit <= 0 || e.modulation_limit > 1
    error('DCAC:Request','modulation_limit must be in (0,1].');
end
devicePositive={'device_rds_on_ohm','device_diode_ron_ohm','device_rise_time_s', ...
    'device_fall_time_s','device_reverse_recovery_charge_c'};
for k=1:numel(devicePositive), requirePositiveScalar(e.(devicePositive{k}),['electrical.' devicePositive{k}]); end
requireNonnegativeScalar(e.device_diode_vf_v,'electrical.device_diode_vf_v');
requireNonnegativeScalar(e.load_breaker_on_resistance_ohm,'electrical.load_breaker_on_resistance_ohm');
requirePositiveScalar(e.soft_start_s,'electrical.soft_start_s');
requireNonnegativeScalar(e.controller_kp_per_v,'electrical.controller_kp_per_v');
requireNonnegativeScalar(e.controller_kr_per_v,'electrical.controller_kr_per_v');
requirePositiveScalar(e.controller_bandwidth_hz,'electrical.controller_bandwidth_hz');
requirePositiveScalar(e.device_junction_temperature_c,'electrical.device_junction_temperature_c');
if ~islogical(e.closed_loop_dead_time_compensation) || ...
        ~isscalar(e.closed_loop_dead_time_compensation)
    error('DCAC:Request','electrical.closed_loop_dead_time_compensation must be a logical scalar.');
end
if ~islogical(e.export_full_csv) || ~isscalar(e.export_full_csv) || ...
        ~islogical(e.export_legacy_csv) || ~isscalar(e.export_legacy_csv) || ...
        ~islogical(e.export_legacy_mat) || ~isscalar(e.export_legacy_mat)
    error('DCAC:Request','electrical export flags must be logical scalars.');
end
if sqrt(2)*s.output_voltage/s.input_voltage > e.modulation_limit
    error('DCAC:Request','Required modulation exceeds the configured limit.');
end
fLC = 1/(2*pi*sqrt(s.inductance*s.capacitance));
if fLC <= 5*s.output_frequency || fLC >= s.switching_frequency/4
    error('DCAC:Request','LC resonance must be above 5*fout and below fsw/4 for this template.');
end
if isStepScenario(e.scenario_id) && ...
        s.load_step_time > s.stop_time-4/s.output_frequency-0.02
    error('DCAC:Request','Load step must precede the final four-cycle window by 20 ms.');
end
if isStepScenario(e.scenario_id) && s.load_step_time < e.soft_start_s+2/s.output_frequency
    error('DCAC:Request','Load step must follow soft start by at least two fundamental cycles.');
end

e.fixed_step_s = 1/(s.switching_frequency*e.steps_per_switching_period);
if startsWith(e.model_fidelity,'sps_')
    e.solver_name='FixedStepDiscrete';
    e.solver_type='fixed_step_discrete';
else
    e.solver_name='ode4';
    e.solver_type='fixed_step_continuous';
end
e.dead_time_resolution_points = e.dead_time_s/e.fixed_step_s;
e.base_modulation_index = sqrt(2)*s.output_voltage/s.input_voltage;
e.dead_time_compensation_index = 0;
if strcmp(e.model_fidelity,'sps_device_closed_loop') && ...
        e.closed_loop_dead_time_compensation
    e.dead_time_compensation_index = 8*s.switching_frequency*e.dead_time_s/pi;
end
e.feedforward_modulation_index = e.base_modulation_index + ...
    e.dead_time_compensation_index;
if e.feedforward_modulation_index > e.modulation_limit
    error('DCAC:Request', ...
        'Base plus dead-time feedforward modulation exceeds the configured limit.');
end
if startsWith(e.model_fidelity,'sps_') && e.dead_time_s>0 && e.dead_time_resolution_points<4
    error('DCAC:Request','SPS stages require at least four fixed steps across dead_time_s.');
end
e.load_ratio_initial = 1.0;
e.load_ratio_final = 1.0;
if strcmp(e.scenario_id,'half_load')
    e.load_ratio_initial = 0.5; e.load_ratio_final = 0.5;
elseif isStepScenario(e.scenario_id)
    if s.load_final_ratio>=1
        error('DCAC:Request','A load-step scenario requires load_final_ratio below 1.');
    end
    e.load_ratio_final = s.load_final_ratio;
end
e.load_step_enabled=isStepScenario(e.scenario_id);
e.legacy_load_step_requested=logical(s.load_step);
e.legacy_condition_overridden=~strcmp(e.scenario_id,scenarioFromLegacy(s));

context = struct('session_id','','run_id','','design_revision',[], ...
    'component_revision_id','','parent_component_revision_id','', ...
    'comparison_group_id','','comparison_peer_run_ids',{{}});
if isfield(request,'run_context'), context = mergeStruct(context,request.run_context); end
end

function value = scenarioFromLegacy(s)
if islogical(s.load_step) && s.load_step
    if abs(s.load_final_ratio-0.5)<1e-12, value='rated_to_half'; else, value='load_step'; end
else
    value = 'rated';
end
end

function yes=isStepScenario(value)
yes=strcmp(value,'rated_to_half') || strcmp(value,'load_step');
end

function out = setDefault(in,name,value)
out = in;
if ~isfield(out,name) || isempty(out.(name)), out.(name) = value; end
end

function out = mergeStruct(base,extra)
out = base;
names = fieldnames(extra);
for k=1:numel(names), out.(names{k}) = extra.(names{k}); end
end

function requirePositiveScalar(value,name)
if ~isnumeric(value) || ~isscalar(value) || ~isfinite(value) || value<=0
    error('DCAC:Request','%s must be a positive finite numeric scalar.',name);
end
end

function requireNonnegativeScalar(value,name)
if ~isnumeric(value) || ~isscalar(value) || ~isfinite(value) || value<0
    error('DCAC:Request','%s must be a nonnegative finite numeric scalar.',name);
end
end
