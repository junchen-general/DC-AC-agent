function result = analyze_e70_switching_ripple()
% Full-rate E70 circuit ripple; linear B conversion is a screening proxy.
root=fileparts(mfilename('fullpath'));
a=jsondecode(fileread(fullfile(root,'material_assumptions.json')));
e=a.e70_alternative_screening;
names={'E70FE68_500W','E70FE68_750W'};
result=struct([]);
for k=1:numel(names)
    folder=fullfile(root,'outputs',['electrical_reference_400_' names{k}]);
    d=load(fullfile(folder,'simulation.mat'));
    r=jsondecode(fileread(fullfile(folder,'handoff_local.json')));
    assert(r.ok);
    dt=r.metrics.sample_time;
    fs=r.spec.switching_frequency;
    f0=r.spec.output_frequency;
    ns=round(1/fs/dt);
    nw=4*round(fs/f0);
    assert(abs(ns*dt*fs-1)<1e-10);
    assert(numel(d.t)>ns*nw);
    current=reshape(d.y(end-ns*nw:end-1,2),ns,nw);
    time=reshape(d.t(end-ns*nw:end-1),ns,nw);
    pp=max(current,[],1)-min(current,[],1);
    residual=current-mean(current,1);
    bpa=r.spec.inductance/(e.turns*e.catalog_Ae_m2);
    q=sort(pp);
    row=struct('case_name',names{k}, ...
        'status','linear_circuit_ripple_envelope_not_core_loss_or_counted_minor_loop', ...
        'samples_per_switch',ns,'switching_periods_analyzed',nw, ...
        'time_window_s',[time(1,1),time(end,end)], ...
        'current_pp_mean_A',mean(pp),'current_pp_p95_A',q(ceil(.95*numel(q))), ...
        'current_pp_max_A',max(pp),'B_per_A_T_per_A',bpa, ...
        'B_pp_mean_T',bpa*mean(pp),'B_pp_p95_T',bpa*q(ceil(.95*numel(q))), ...
        'B_pp_max_T',bpa*max(pp), ...
        'current_period_demeaned_rms_A',sqrt(mean(residual(:).^2)), ...
        'Rdc_period_demeaned_loss_W',r.spec.winding_resistance*mean(residual(:).^2), ...
        'current_full_rms_A',sqrt(mean(current(:).^2)), ...
        'Rdc_full_loss_W',r.spec.winding_resistance*mean(current(:).^2), ...
        'note','B uses L/(N*Ae) linear proxy; period range is not a counted hysteresis loop; Rdc term is not AC excess loss');
    assert(abs(row.Rdc_full_loss_W/r.metrics.winding_loss-1)<1e-8);
    if k==1
        result=row;
    else
        result(k)=row;
    end
end
fid=fopen(fullfile(root,'outputs','e70_switching_ripple.json'),'w','n','UTF-8');
fprintf(fid,'%s',jsonencode(result,PrettyPrint=true)); fclose(fid);
disp(result);
end
