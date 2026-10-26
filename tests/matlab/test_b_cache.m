function test_b_cache()
% Synthetic executor verifies cache behavior only; not physical evidence.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
baseDir=fullfile(root,'work','b-cache-tests');if ~isfolder(baseDir),mkdir(baseDir);end
scratch=tempname(baseDir);mkdir(scratch);
for name={'dcac_validate.m','dcac_compare_step_runs.m','dcac_write_json.m'}
 copyfile(fullfile(root,'matlab','electrical',name{1}),scratch);
end
stub=fullfile(scratch,'dcac_execute.m');
lines={ ...
 'function dcac_execute(path)', ...
 'global B_CACHE_TEST_CALLS;B_CACHE_TEST_CALLS=B_CACHE_TEST_CALLS+1;', ...
 'q=jsondecode(fileread(path));', ...
 'data=struct(''ok'',true,''spec'',q.spec,''electrical_v1'',q.electrical);', ...
 'data.solver=struct(''steps_per_switching_period'',q.electrical.steps_per_switching_period);', ...
 'data.metrics=struct(''output_rms'',220,''thd_percent'',1,''inductor_rms'',2,''inductor_peak'',4,''output_power'',500,''winding_loss'',1);', ...
 'dcac_write_json(fullfile(q.output_dir,''result.json''),data);', ...
 't=0;signals=struct;meta=struct;context=struct;', ...
 'save(fullfile(q.output_dir,''electrical_raw_v1.mat''),''t'',''signals'',''meta'',''context'');', ...
 'end'};
fid=fopen(stub,'w');fprintf(fid,'%s\n',lines{:});fclose(fid);
addpath(scratch,'-begin');cleanup=onCleanup(@()rmpath(scratch)); %#ok<NASGU>
clear dcac_validate dcac_execute dcac_compare_step_runs dcac_write_json
q=struct('output_dir',fullfile(scratch,'out'),'spec',struct('switching_frequency',20000,'input_voltage',380),'electrical',struct);
mkdir(q.output_dir);path=fullfile(scratch,'request.json');dcac_write_json(path,q);
global B_CACHE_TEST_CALLS;B_CACHE_TEST_CALLS=0;
dcac_validate(path,'baseline',[400 800]);assert(B_CACHE_TEST_CALLS==6);
dcac_validate(path,'baseline',[400 800]);assert(B_CACHE_TEST_CALLS==6,'Identical request should reuse cache');
q.spec.input_voltage=390;dcac_write_json(path,q);
dcac_validate(path,'baseline',[400 800]);assert(B_CACHE_TEST_CALLS==12,'Changed spec must invalidate cache');
fid=fopen(stub,'a');fprintf(fid,'\n%% changed source\n');fclose(fid);
dcac_validate(path,'baseline',[400 800]);assert(B_CACHE_TEST_CALLS==18,'Changed source must invalidate cache');
% An incomplete raw export cannot be reused even when result.json says OK.
t=0;save(fullfile(q.output_dir,'validation','baseline_ideal_switching_open_loop__rated__n400','electrical_raw_v1.mat'),'t');
dcac_validate(path,'baseline',[400 800]);assert(B_CACHE_TEST_CALLS==19,'Missing raw signals must rerun');
fprintf('B_CACHE_REGRESSIONS_PASS\n');
end
