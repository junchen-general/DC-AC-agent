function summary = dcac_validate(requestPath,profile)
%DCAC_VALIDATE Run the reproducible operating-condition/time-step matrix.
% profile='baseline' runs 3 scenarios x 2 steps on Stage 0.
% profile='full' runs all four fidelity stages. This can be expensive.
if nargin<2, profile='full'; end
base=jsondecode(fileread(requestPath));
root=char(base.output_dir);
validationRoot=fullfile(root,'validation');
if ~isfolder(validationRoot), mkdir(validationRoot); end
if strcmp(profile,'baseline')
    stages={'baseline_ideal_switching_open_loop'};
elseif strcmp(profile,'full')
    stages={'baseline_ideal_switching_open_loop','sps_device_open_loop', ...
        'sps_device_lossy_open_loop','sps_device_closed_loop'};
else
    error('DCAC:Validation','profile must be baseline or full.');
end
scenarios={'rated','half_load','rated_to_half'};
rows=struct('stage',{},'scenario',{},'steps_per_switching_period',{},'fixed_step_s',{}, ...
    'status',{},'output_rms_V',{},'thd_h2_h40_percent',{},'inductor_rms_A',{}, ...
    'inductor_peak_A',{},'output_power_W',{},'winding_loss_W',{}, ...
    'run_id',{},'comparison_group_id',{},'result_path',{},'error',{});
for a=1:numel(stages)
    if strcmp(stages{a},'baseline_ideal_switching_open_loop'), stepCounts=[100 200]; else, stepCounts=[200 400]; end
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
            caseRequest=fullfile(caseDir,'request.json'); dcac_write_json(caseRequest,req);
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
                        reusable=isfield(data,'ok') && data.ok && isfield(data,'electrical_v1') && ...
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
comparison=comparePairs(rows);
summary=struct('schema_version','dcac.time-step-study/1.0','profile',profile, ...
    'created_utc',char(datetime('now','TimeZone','UTC')),'runs',rows,'comparisons',comparison, ...
    'criteria',struct('output_rms_relative_percent',0.2,'inductor_rms_relative_percent',0.5, ...
    'inductor_peak_relative_percent',1.0,'thd_absolute_percentage_points',0.1), ...
    'limitation','Success requires real MATLAB compilation/simulation; failed cases retain result.json and logs.');
dcac_write_json(fullfile(validationRoot,'time_step_study_v1.json'),summary);
writetable(struct2table(rows),fullfile(validationRoot,'time_step_runs_v1.csv'));
writetable(struct2table(comparison),fullfile(validationRoot,'time_step_comparison_v1.csv'));
% Root-level copies remain visible to the current non-recursive Agent artifact scanner.
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

function comparisons=comparePairs(rows)
comparisons=struct('stage',{},'scenario',{},'coarse_steps',{},'fine_steps',{}, ...
    'output_rms_relative_percent',{},'thd_absolute_percentage_points',{}, ...
    'inductor_rms_relative_percent',{},'inductor_peak_relative_percent',{},'converged',{}, ...
    'comparison_group_id',{},'coarse_run_id',{},'fine_run_id',{},'selected_run_id',{});
stages=unique({rows.stage}); scenarios=unique({rows.scenario});
for a=1:numel(stages)
    for b=1:numel(scenarios)
        pair=rows(strcmp({rows.stage},stages{a}) & strcmp({rows.scenario},scenarios{b}) & strcmp({rows.status},'success'));
        if numel(pair)~=2, continue; end
        [~,order]=sort([pair.steps_per_switching_period]); pair=pair(order);
        out=relative(pair(1).output_rms_V,pair(2).output_rms_V);
        thd=abs(pair(1).thd_h2_h40_percent-pair(2).thd_h2_h40_percent);
        ir=relative(pair(1).inductor_rms_A,pair(2).inductor_rms_A);
        ip=relative(pair(1).inductor_peak_A,pair(2).inductor_peak_A);
        comparisons(end+1)=struct('stage',stages{a},'scenario',scenarios{b}, ...
            'coarse_steps',pair(1).steps_per_switching_period,'fine_steps',pair(2).steps_per_switching_period, ...
            'output_rms_relative_percent',out,'thd_absolute_percentage_points',thd, ...
            'inductor_rms_relative_percent',ir,'inductor_peak_relative_percent',ip, ...
            'converged',out<0.2 && thd<0.1 && ir<0.5 && ip<1.0, ...
            'comparison_group_id',pair(1).comparison_group_id, ...
            'coarse_run_id',pair(1).run_id,'fine_run_id',pair(2).run_id, ...
            'selected_run_id',pair(2).run_id); %#ok<AGROW>
    end
end
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
    manifest.step_size_comparison=struct('status','complete', ...
        'comparison_group_id',comparison.comparison_group_id, ...
        'peer_run_ids',{{comparison.coarse_run_id,comparison.fine_run_id}}, ...
        'study_path','../time_step_study_v1.json','converged',comparison.converged, ...
        'selected_run_id',comparison.selected_run_id, ...
        'this_run_selected',strcmp(rows(k).run_id,comparison.selected_run_id), ...
        'deltas',struct('output_rms_relative_percent',comparison.output_rms_relative_percent, ...
        'thd_absolute_percentage_points',comparison.thd_absolute_percentage_points, ...
        'inductor_rms_relative_percent',comparison.inductor_rms_relative_percent, ...
        'inductor_peak_relative_percent',comparison.inductor_peak_relative_percent));
    dcac_write_json(path,manifest);
end
end

function value=relative(a,b)
value=100*abs(a-b)/max(abs(b),eps);
end
