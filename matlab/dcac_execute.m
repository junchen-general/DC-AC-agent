function dcac_execute(requestPath)
%DCAC_EXECUTE Build, compile, simulate, and export one selected fidelity stage.
% The existing Python/Agent contract remains unchanged. Additive electrical
% options live in request.electrical and additive results in electrical_v1.
baseDir=fileparts(mfilename('fullpath'));
addpath(baseDir);
supportDir=fullfile(baseDir,'electrical');
if isfolder(supportDir), addpath(supportDir); end

phase='read_request';
request=struct; s=struct; e=struct; context=struct;
outdir=fileparts(requestPath);
resultPath=fullfile(outdir,'result.json');
mdl='dcac_inverter';
try
    request=jsondecode(fileread(requestPath));
    if isfield(request,'output_dir'), outdir=char(request.output_dir); end
    if ~isfolder(outdir), mkdir(outdir); end
    resultPath=fullfile(outdir,'result.json');
    phase='validate_request';
    [s,e,context]=dcac_normalize_request(request);

    phase='prepare_model';
    modelPath=fullfile(outdir,[mdl '.slx']);
    protectLoadedModel(mdl,modelPath);
    if strcmp(e.model_fidelity,'baseline_ideal_switching_open_loop')
        dcac_build_baseline_model(mdl,s,e);
    else
        dcac_build_sps_model(mdl,s,e);
    end
    cleanup=onCleanup(@() closeIfLoaded(mdl)); %#ok<NASGU>

    phase='compile_model';
    set_param(mdl,'SimulationCommand','update');
    phase='save_model';
    save_system(mdl,modelPath);
    result=struct('ok',true,'schema_version','dcac.result/1.1', ...
        'action',request.action,'source','MATLAB/Simulink','data_origin','real_model_compile', ...
        'matlab_version',version,'model_level',legacyModelLevel(e.model_fidelity), ...
        'model_path',modelPath,'model_file','dcac_inverter.slx','spec',s, ...
        'run_context',context,'scenario',e.scenario_id, ...
        'solver',struct('type',e.solver_type,'name',e.solver_name,'fixed_step_s',e.fixed_step_s, ...
        'steps_per_switching_period',e.steps_per_switching_period), ...
        'electrical_v1',struct('schema_version',e.schema_version, ...
        'model_fidelity',e.model_fidelity,'scenario_id',e.scenario_id, ...
        'dead_time_s',e.dead_time_s,'dead_time_resolution_points',e.dead_time_resolution_points, ...
        'dead_time_requested_s',e.dead_time_requested_s,'dead_time_effective_s',e.dead_time_effective_s, ...
        'dead_time_discrete_steps',e.dead_time_discrete_steps,'dead_time_quantization_error_s',e.dead_time_quantization_error_s, ...
        'closed_loop_dead_time_compensation',e.closed_loop_dead_time_compensation, ...
        'base_modulation_index',e.base_modulation_index, ...
        'dead_time_compensation_index',e.dead_time_compensation_index, ...
        'feedforward_modulation_index',e.feedforward_modulation_index, ...
        'compiled',true,'simulated',false));

    if strcmp(request.action,'simulate')
        phase='simulate';
        simulation=sim(mdl);
        phase='postprocess';
        result=dcac_postprocess(simulation,s,e,context,outdir,result);
        result.electrical_v1.compiled=true;
        result.electrical_v1.simulated=true;
        result.data_origin='real_simulation';
    elseif ~strcmp(request.action,'build')
        error('DCAC:Request','Unsupported action: %s',request.action);
    end

    phase='write_result';
    dcac_write_json(resultPath,result);
    phase='write_manifest';
    dcac_write_manifest(outdir,request,result,'dcac_inverter.slx');
    fprintf('DCAC_SUCCESS %s\n',resultPath);
catch err
    result=struct('ok',false,'schema_version','dcac.result/1.1','phase',phase, ...
        'error',err.message,'identifier',err.identifier, ...
        'report',getReport(err,'extended','hyperlinks','off'));
    if ~isempty(fieldnames(s)), result.spec=s; end
    if ~isempty(fieldnames(e)) && isfield(e,'model_fidelity')
        result.model_level=legacyModelLevel(e.model_fidelity);
        if isfield(e,'scenario_id'), result.scenario=e.scenario_id; end
    end
    try
        dcac_write_json(resultPath,result);
        if ~isempty(fieldnames(request)) && isfield(request,'action')
            dcac_write_manifest(outdir,request,result,'dcac_inverter.slx');
        end
    catch writeError
        fprintf(2,'DCAC result/manifest write failure: %s\n',writeError.message);
    end
    fprintf(2,'%s\n',result.report);
    rethrow(err);
end
end

function value=legacyModelLevel(fidelity)
if strcmp(fidelity,'baseline_ideal_switching_open_loop')
    value='ideal_switching_function_open_loop';
else
    value=fidelity;
end
end

function protectLoadedModel(mdl,expectedPath)
if ~bdIsLoaded(mdl), return; end
loadedPath=get_param(mdl,'FileName');
if isempty(loadedPath) || ~samePath(loadedPath,expectedPath)
    error('DCAC:ModelNameCollision',[ ...
        'A different model named %s is already loaded. Save or close it before running; ' ...
        'the automation will not discard an unrelated unsaved model.'],mdl);
end
close_system(mdl,0);
end

function yes=samePath(left,right)
try
    left=char(java.io.File(left).getCanonicalPath());
    right=char(java.io.File(right).getCanonicalPath());
catch
    left=char(left); right=char(right);
end
if ispc, yes=strcmpi(left,right); else, yes=strcmp(left,right); end
end

function closeIfLoaded(mdl)
if bdIsLoaded(mdl), close_system(mdl,0); end
end
