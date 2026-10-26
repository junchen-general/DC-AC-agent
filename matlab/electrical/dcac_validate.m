function summary = dcac_validate(requestPath,profile,stepCountsOverride)
%DCAC_VALIDATE Run the reproducible operating-condition/time-step matrix.
% profile='baseline' runs 3 scenarios x 2 steps on Stage 0.
% profile='full' runs all four fidelity stages. This can be expensive.
% profile can also be an exact model_fidelity name for targeted refinement.
if nargin<2, profile='full'; end
if nargin<3, stepCountsOverride=[]; end
if ~isempty(stepCountsOverride)
    validateattributes(stepCountsOverride,{'numeric'},{'vector','numel',2,'integer','>=',20,'<=',3200});
    assert(stepCountsOverride(1)<stepCountsOverride(2),'Steps must be increasing.');
end
sourceHash=solverFingerprint();
base=jsondecode(fileread(requestPath));
root=char(base.output_dir);
validationRoot=fullfile(root,'validation');
if ~isfolder(validationRoot), mkdir(validationRoot); end
if strcmp(profile,'baseline')
    stages={'baseline_ideal_switching_open_loop'};
elseif strcmp(profile,'full')
    stages={'baseline_ideal_switching_open_loop','sps_device_open_loop', ...
        'sps_device_lossy_open_loop','sps_device_closed_loop'};
elseif any(strcmp(profile,{'baseline_ideal_switching_open_loop','sps_device_open_loop', ...
        'sps_device_lossy_open_loop','sps_device_closed_loop'}))
    stages={profile};
else
    error('DCAC:Validation','profile must be baseline, full, or an exact model_fidelity name.');
end
scenarios={'rated','half_load','rated_to_half'};
rows=struct('stage',{},'scenario',{},'steps_per_switching_period',{},'fixed_step_s',{}, ...
    'status',{},'output_rms_V',{},'thd_h2_h40_percent',{},'inductor_rms_A',{}, ...
    'inductor_peak_A',{},'output_power_W',{},'winding_loss_W',{}, ...
    'run_id',{},'comparison_group_id',{},'result_path',{},'error',{});
for a=1:numel(stages)
    if strcmp(stages{a},'baseline_ideal_switching_open_loop'), stepCounts=[100 200]; else, stepCounts=[200 400]; end
    if ~isempty(stepCountsOverride),stepCounts=stepCountsOverride;end
    for b=1:numel(scenarios)
        for c=1:numel(stepCounts)
            tag=sprintf('%s__%s__n%d',stages{a},scenarios{b},stepCounts(c));
            groupId=sprintf('%s__%s',stages{a},scenarios{b});
            peerIds=arrayfun(@(n) sprintf('%s__%s__n%d',stages{a},scenarios{b},n), ...
                stepCounts,'UniformOutput',false);
            caseDir=fullfile(validationRoot,tag); if ~isfolder(caseDir), mkdir(caseDir); end
            req=base; req.action='simulate'; req.output_dir=caseDir;
            req.electrical.model_fidelity=stages{a}; req.electrical.scenario_id=scenarios{b};
            req.electrical.steps_per_switching_period=stepCounts(c);
            req.electrical.closed_loop_dead_time_compensation=strcmp(stages{a}, ...
                'sps_device_closed_loop');
            % Each matrix case retains the authoritative full-resolution MAT.
            % Redundant full/legacy CSV files are omitted to keep a 24-run study bounded.
            req.electrical.export_full_csv=false;
            req.electrical.export_legacy_csv=false;
            req.electrical.export_legacy_mat=false;
            if ~isfield(req,'run_context'), req.run_context=struct; end
            req.run_context.run_id=tag;
            req.run_context.comparison_group_id=groupId;
            req.run_context.comparison_peer_run_ids=peerIds;
            % Keep spec aligned with the chosen stage/scenario for downstream users.
            req.spec.model_fidelity=stages{a};
            req.spec.load_step=strcmp(scenarios{b},'rated_to_half');
            % JSON round-trip normalizes cell-array orientation before exact
            % comparison (jsondecode returns string arrays as column cells).
            req=jsondecode(jsonencode(req));
            caseRequest=fullfile(caseDir,'request.json');
            cacheRequest=fullfile(caseDir,'validation_request_snapshot.json');
            cacheSource=fullfile(caseDir,'validation_source_sha256.txt');
            requestMatches=false;
            try
                previous=jsondecode(fileread(cacheRequest));
                requestMatches=isequaln(previous,req) && strcmp(strtrim(fileread(cacheSource)),sourceHash);
            catch
                % Old studies without an exact request/source fingerprint are not reused.
            end
            dcac_write_json(caseRequest,req);
            row=emptyRow(stages{a},scenarios{b},stepCounts(c), ...
                1/(req.spec.switching_frequency*stepCounts(c)),tag,groupId,caseDir);
            try
                resultFile=fullfile(caseDir,'result.json');
                if isfile(resultFile)
                    % A previous disk-full or interrupted run can leave an
                    % empty/truncated JSON file.  Treat it as non-reusable
                    % instead of failing the matrix before dcac_execute gets
                    % a chance to replace it.
                    try
                        data=jsondecode(fileread(resultFile));
                        reusable=requestMatches && completeRawFile(fullfile(caseDir,'electrical_raw_v1.mat')) && ...
                            isfield(data,'spec') && isequaln(data.spec,req.spec) && isfield(data,'ok') && data.ok && isfield(data,'electrical_v1') && ...
                            strcmp(data.electrical_v1.model_fidelity,stages{a}) && ...
                            strcmp(data.electrical_v1.scenario_id,scenarios{b}) && ...
                            isfield(data,'solver') && ...
                            data.solver.steps_per_switching_period==stepCounts(c);
                        if strcmp(stages{a},'sps_device_closed_loop')
                            reusable=reusable && ...
                                isfield(data.electrical_v1,'closed_loop_dead_time_compensation') && ...
                                data.electrical_v1.closed_loop_dead_time_compensation;
                        end
                    catch
                        reusable=false;
                    end
                else
                    reusable=false;
                end
                if ~reusable
                    dcac_execute(caseRequest);
                    data=jsondecode(fileread(resultFile));
                end
                if data.ok
                    dcac_write_json(cacheRequest,req);
                    fid=fopen(cacheSource,'w');fprintf(fid,'%s',sourceHash);fclose(fid);
                    row.status='success'; row.output_rms_V=data.metrics.output_rms;
                    row.thd_h2_h40_percent=data.metrics.thd_percent;
                    row.inductor_rms_A=data.metrics.inductor_rms;
                    row.inductor_peak_A=data.metrics.inductor_peak;
                    row.output_power_W=data.metrics.output_power;
                    row.winding_loss_W=data.metrics.winding_loss;
                else
                    row.status='failed'; row.error=data.error;
                end
            catch err
                row.status='failed'; row.error=err.message;
            end
            rows(end+1)=row; %#ok<AGROW>
        end
    end
end
comparison=dcac_compare_step_runs(rows);
summary=struct('schema_version','dcac.time-step-study/1.0','profile',profile, ...
    'solver_source_sha256',sourceHash,'created_utc',char(datetime('now','TimeZone','UTC')),'runs',rows,'comparisons',comparison, ...
    'criteria',struct('output_rms_relative_percent',0.2,'inductor_rms_relative_percent',0.5, ...
    'inductor_peak_relative_percent',1.0,'thd_absolute_percentage_points',0.1), ...
    'limitation','Success requires real MATLAB compilation/simulation; failed cases retain result.json and logs.');
dcac_write_json(fullfile(validationRoot,'time_step_study_v1.json'),summary);
writetable(struct2table(rows),fullfile(validationRoot,'time_step_runs_v1.csv'));
writetable(struct2table(comparison),fullfile(validationRoot,'time_step_comparison_v1.csv'));
% Root-level copies provide convenient entry points for Agent downloads.
dcac_write_json(fullfile(root,'time_step_study_v1.json'),summary);
writetable(struct2table(rows),fullfile(root,'time_step_runs_v1.csv'));
writetable(struct2table(comparison),fullfile(root,'time_step_comparison_v1.csv'));
bindComparisonManifests(rows,comparison);
end

function row=emptyRow(stage,scenario,steps,dt,runId,groupId,path)
row=struct('stage',stage,'scenario',scenario,'steps_per_switching_period',steps, ...
    'fixed_step_s',dt,'status','not_run','output_rms_V',NaN,'thd_h2_h40_percent',NaN, ...
    'inductor_rms_A',NaN,'inductor_peak_A',NaN,'output_power_W',NaN, ...
    'winding_loss_W',NaN,'run_id',runId,'comparison_group_id',groupId, ...
    'result_path',path,'error','');
end

function bindComparisonManifests(rows,comparisons)
for k=1:numel(rows)
    if ~strcmp(rows(k).status,'success'), continue; end
    selected=find(strcmp({comparisons.comparison_group_id},rows(k).comparison_group_id),1);
    if isempty(selected), continue; end
    comparison=comparisons(selected);
    path=fullfile(rows(k).result_path,'run_manifest.json');
    if ~isfile(path), continue; end
    manifest=jsondecode(fileread(path));
    manifest.step_size_comparison=struct('status',comparison.status, ...
        'comparison_group_id',comparison.comparison_group_id, ...
        'peer_run_ids',{{comparison.coarse_run_id,comparison.fine_run_id}}, ...
        'study_path','../time_step_study_v1.json','converged',comparison.converged, ...
        'failed_criteria',comparison.failed_criteria, ...
        'selected_run_id',comparison.selected_run_id, ...
        'this_run_selected',strcmp(rows(k).run_id,comparison.selected_run_id), ...
        'deltas',struct('output_rms_relative_percent',comparison.output_rms_relative_percent, ...
        'thd_absolute_percentage_points',comparison.thd_absolute_percentage_points, ...
        'inductor_rms_relative_percent',comparison.inductor_rms_relative_percent, ...
        'inductor_peak_relative_percent',comparison.inductor_peak_relative_percent));
    dcac_write_json(path,manifest);
end
end

function hash=solverFingerprint()
root=fileparts(mfilename('fullpath'));
files=dir(fullfile(root,'*.m'));
[~,order]=sort({files.name});files=files(order);
md=java.security.MessageDigest.getInstance('SHA-256');
for k=1:numel(files)
    md.update(unicode2native(files(k).name,'UTF-8'));
    fid=fopen(fullfile(root,files(k).name),'rb');bytes=fread(fid,inf,'*uint8');fclose(fid);md.update(bytes);
end
entry=fullfile(root,'..','dcac_execute.m');
if isfile(entry)
    fid=fopen(entry,'rb');bytes=fread(fid,inf,'*uint8');fclose(fid);md.update(bytes);
end
hash=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end

function valid=completeRawFile(path)
valid=false;
if ~isfile(path),return;end
try
    vars=whos('-file',path);
    valid=all(ismember({'t','signals','meta','context'},{vars.name}));
catch
    % Truncated MAT files and v7 exports missing a >2 GB signals struct rerun.
end
end
