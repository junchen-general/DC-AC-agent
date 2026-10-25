function summary = dcac_build_stages(requestPath)
%DCAC_BUILD_STAGES Build/update/compile each fidelity stage without simulating.
base=jsondecode(fileread(requestPath)); root=char(base.output_dir);
stageRoot=fullfile(root,'model_stages'); if ~isfolder(stageRoot), mkdir(stageRoot); end
stages={'baseline_ideal_switching_open_loop','sps_device_open_loop', ...
    'sps_device_lossy_open_loop','sps_device_closed_loop'};
summary=repmat(struct('stage','','status','','model','','error',''),1,numel(stages));
for k=1:numel(stages)
    folder=fullfile(stageRoot,stages{k}); if ~isfolder(folder), mkdir(folder); end
    req=base; req.action='build'; req.output_dir=folder; req.electrical.model_fidelity=stages{k};
    req.electrical.closed_loop_dead_time_compensation=strcmp(stages{k}, ...
        'sps_device_closed_loop');
    if strcmp(stages{k},'baseline_ideal_switching_open_loop')
        req.electrical.steps_per_switching_period=100;
    else
        req.electrical.steps_per_switching_period=200;
    end
    path=fullfile(folder,'request.json'); dcac_write_json(path,req);
    summary(k).stage=stages{k}; summary(k).model=fullfile(folder,'dcac_inverter.slx');
    try
        dcac_execute(path); data=jsondecode(fileread(fullfile(folder,'result.json')));
        if data.ok, summary(k).status='compiled'; else, summary(k).status='failed'; summary(k).error=data.error; end
    catch err
        summary(k).status='failed'; summary(k).error=err.message;
    end
end
dcac_write_json(fullfile(stageRoot,'build_summary_v1.json'),summary);
dcac_write_json(fullfile(root,'model_stage_build_summary_v1.json'),summary);
end
