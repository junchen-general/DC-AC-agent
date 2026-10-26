% Focused MATLAB regressions: do not run physical cases.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
addpath(fullfile(root,'matlab','electrical'));
base=struct('stage','test','scenario','rated','steps_per_switching_period',400, ...
 'status','success','output_rms_V',220,'thd_h2_h40_percent',1,'inductor_rms_A',2, ...
 'inductor_peak_A',4,'comparison_group_id','test-rated','run_id','coarse');
fine=base;fine.steps_per_switching_period=800;fine.run_id='fine';
c=dcac_compare_step_runs([base,fine]);assert(c.converged && strcmp(c.status,'complete'));
fine.inductor_peak_A=4.1;c=dcac_compare_step_runs([base,fine]);assert(~c.converged && contains(c.failed_criteria,'inductor_peak'));
fine.status='failed';c=dcac_compare_step_runs([base,fine]);assert(~c.converged && strcmp(c.status,'incomplete'));
c=dcac_compare_step_runs(base);assert(strcmp(c.status,'incomplete'));
fine=base;fine.steps_per_switching_period=800;fine.inductor_peak_A=NaN;
c=dcac_compare_step_runs([base,fine]);assert(strcmp(c.status,'incomplete'));
% Requested dead time below one tick must not round to zero and bypass validation.
s=struct('input_voltage',380,'output_voltage',220,'output_power',500, ...
 'output_frequency',50,'switching_frequency',20000,'inductance',.002, ...
 'capacitance',4.7e-6,'winding_resistance',.25,'stop_time',.24, ...
 'load_step',false,'load_step_time',.12,'load_final_ratio',.5);
req=struct('spec',s,'electrical',struct('model_fidelity','sps_device_open_loop', ...
 'steps_per_switching_period',400,'dead_time_s',1e-8));
rejected=false;
try,dcac_normalize_request(req);catch err,rejected=strcmp(err.identifier,'DCAC:Request');end
assert(rejected);
req.electrical.dead_time_s=1.02e-6;
[~,e]=dcac_normalize_request(req);
assert(abs(e.dead_time_effective_s-1e-6)<1e-15);
assert(abs(e.dead_time_quantization_error_s+2e-8)<1e-15);
% FIR qualification must delay rise exactly N ticks, drop immediately and suppress short pulses.
N=8;u=[zeros(1,5),ones(1,3),zeros(1,20),ones(1,20),zeros(1,5)];
g=filter(ones(1,N+1),1,u)>=N+.5;
assert(~any(g(1:28)));assert(find(g,1)==29+N);assert(~g(49));
% Check source parser, without relying on a stale compiled model.
files={'dcac_validate','dcac_compare_step_runs','dcac_build_sps_model','dcac_normalize_request'};
for k=1:numel(files)
 issues=checkcode(which(files{k}),'-id');
 assert(~any(strcmp({issues.id},'PARSE')),'MATLAB source parse error');
end
fprintf('B_AUDIT_REGRESSIONS_PASS\n');
