function rows=run_e70_combined_scenarios()
% Reuse linear unit FE fields for explicitly assumed two-source heat scenarios.
% Copper R feedback uses peak temperature as a conservative lumped proxy.
root=fileparts(mfilename('fullpath'));
out=fullfile(root,'outputs','e70_combined_scenarios');
if ~isfolder(out),mkdir(out);end
a=load(fullfile(root,'outputs','unit_response_e70','case_02.mat'));
b=load(fullfile(root,'outputs','unit_response_e70','case_03.mat'));
assert(isequal(a.thermal.Mesh.Nodes,b.thermal.Mesh.Nodes));
assert(isequal(a.structural.Mesh.Nodes,b.structural.Mesh.Nodes));
assert(isequal(a.thermal.Mesh.Elements,b.thermal.Mesh.Elements));
assert(isequal(a.structural.Mesh.Elements,b.structural.Mesh.Elements));
assert(a.m.h_W_m2K==10 && b.m.h_W_m2K==10);
assert(a.m.input_power_W==1 && b.m.input_power_W==1);
alpha=.00393; ambient=40;
cases={'E70FE68_500W',.5,.5;'E70FE68_750W',.5,.5};
rows=struct([]);
for k=1:size(cases,1)
    name=cases{k,1}; pac=cases{k,2}; pc=cases{k,3};
    report=jsondecode(fileread(fullfile(root,'outputs',['electrical_reference_400_' name],'handoff_local.json')));
    assert(report.ok);
    p20=report.metrics.winding_loss;
    % T is the vector of nodal rises.  Same-grid field superposition is exact
    % for these fixed linear material and boundary assumptions.
    tmax=ambient;
    for it=1:100
        pdc=p20*(1+alpha*(tmax-20));
        pw=pdc+pac;
        rise=pw*a.temperature.Temperature+pc*b.temperature.Temperature;
        next=ambient+max(rise);
        if abs(next-tmax)<1e-9,break;end
        tmax=next;
    end
    assert(it<100 && abs(next-tmax)<1e-9);
    tmax=next;
    pdc=p20*(1+alpha*(tmax-20)); pw=pdc+pac;
    rise=pw*a.temperature.Temperature+pc*b.temperature.Temperature;
    assert(abs(ambient+max(rise)-tmax)<1e-8);
    ux=pw*a.displacement.Displacement.ux+pc*b.displacement.Displacement.ux;
    uy=pw*a.displacement.Displacement.uy+pc*b.displacement.Displacement.uy;
    umag=hypot(ux,uy);
    sx=pw*a.displacement.Stress.sxx+pc*b.displacement.Stress.sxx;
    sy=pw*a.displacement.Stress.syy+pc*b.displacement.Stress.syy;
    sxy=pw*a.displacement.Stress.sxy+pc*b.displacement.Stress.sxy;
    s1=max(.5*(sx+sy)+hypot(.5*(sx-sy),sxy),0);
    probeX=[0,.029,0]; probeY=[.013,0,.027];
    sa=interpolateStress(a.displacement,probeX,probeY);
    sb=interpolateStress(b.displacement,probeX,probeY);
    px=pw*sa.sxx+pc*sb.sxx;py=pw*sa.syy+pc*sb.syy;
    pxy=pw*sa.sxy+pc*sb.sxy;
    probe=max(.5*(px+py)+hypot(.5*(px-py),pxy),0);
    bound=ambient+pw*a.m.peak_temperature_rise_K_per_W+pc*b.m.peak_temperature_rise_K_per_W;
    assert(tmax<=bound+1e-7);
    row=struct('case_name',name,'status','specified_heat_source_linear_FE_simulation', ...
        'ambient_C',ambient,'h_W_m2K',10,'specified_extra_winding_heat_W',pac, ...
        'specified_core_heat_W',pc,'R20_fixed_circuit_loss_W',p20, ...
        'feedback_DC_copper_loss_W',pdc,'total_winding_heat_W',pw, ...
        'peak_temperature_C',tmax,'upper_bound_from_individual_source_peaks_C',bound, ...
        'max_displacement_m',max(umag),'core_probe_max_tensile_principal_stress_Pa',probe(:)', ...
        'global_nodal_max_tensile_principal_stress_Pa_mesh_sensitive',max(s1), ...
        'thermal_nodes',numel(rise),'structural_nodes',numel(umag), ...
        'thermal_mesh_matching_verified',true,'structural_mesh_matching_verified',true, ...
        'source_case_winding','unit_response_e70/case_02.mat', ...
        'source_case_core','unit_response_e70/case_03.mat', ...
        'note','0.5 W extra winding heat and 0.5 W core heat are specified simulation inputs; no material loss calculation or strength safety factor');
    if k==1,rows=row;else,rows(k)=row;end
    save(fullfile(out,[name '.mat']),'row','rise','ux','uy','umag','sx','sy','sxy','s1','a','b','-v7.3');
    fig=figure('Visible','off','Color','w','Position',[50,50,1450,460]);
    subplot(1,3,1);pdeplot(a.thermal,'XYData',ambient+rise,'Contour','off');
    axis equal tight;title(sprintf('%s: temperature (°C)',name),'Interpreter','none');xlabel('x (m)');ylabel('y (m)');
    subplot(1,3,2);pdeplot(a.structural,'XYData',umag*1e6,'Contour','off');
    axis equal tight;title('Displacement magnitude (µm)');xlabel('x (m)');ylabel('y (m)');
    subplot(1,3,3);pdeplot(a.structural,'XYData',s1/1e6,'Contour','off');
    axis equal tight;title('Max tensile principal stress (MPa; mesh sensitive)');xlabel('x (m)');ylabel('y (m)');
    colormap(parula);
    exportgraphics(fig,fullfile(out,[name '.png']),'Resolution',170);close(fig);
    fprintf('%s Tpeak_C=%.5f Umax_um=%.5f probe_stress_MPa=%.5f\n', ...
        name,tmax,max(umag)*1e6,max(probe)/1e6);
end
fid=fopen(fullfile(out,'metrics.json'),'w','n','UTF-8');
fprintf(fid,'%s',jsonencode(rows,PrettyPrint=true));fclose(fid);
cw=load(fullfile(root,'outputs','unit_response_e70','case_01.mat'));
cc=load(fullfile(root,'outputs','unit_response_e70','core_h10_coarse.mat'));
assert(isequal(cw.thermal.Mesh.Nodes,cc.thermal.Mesh.Nodes));
assert(isequal(cw.structural.Mesh.Nodes,cc.structural.Mesh.Nodes));
p20=rows(2).R20_fixed_circuit_loss_W;
tmax=ambient;
for it=1:100
    pdc=p20*(1+alpha*(tmax-20));
    pw=pdc+.5;
    rise=pw*cw.temperature.Temperature+.5*cc.temperature.Temperature;
    next=ambient+max(rise);
    if abs(next-tmax)<1e-9,break;end
    tmax=next;
end
assert(it<100);
ux=pw*cw.displacement.Displacement.ux+.5*cc.displacement.Displacement.ux;
uy=pw*cw.displacement.Displacement.uy+.5*cc.displacement.Displacement.uy;
sa=interpolateStress(cw.displacement,probeX,probeY);
sb=interpolateStress(cc.displacement,probeX,probeY);
px=pw*sa.sxx+.5*sb.sxx; py=pw*sa.syy+.5*sb.syy;
pxy=pw*sa.sxy+.5*sb.sxy;
probe=max(.5*(px+py)+hypot(.5*(px-py),pxy),0);
check=struct('case_name',rows(2).case_name,'coarse_hmax_m',.002,'fine_hmax_m',.0015, ...
    'coarse_peak_temperature_C',next,'fine_peak_temperature_C',rows(2).peak_temperature_C, ...
    'peak_temperature_change_percent',100*abs(next-rows(2).peak_temperature_C)/rows(2).peak_temperature_C, ...
    'coarse_max_displacement_m',max(hypot(ux,uy)), ...
    'fine_max_displacement_m',rows(2).max_displacement_m, ...
    'max_displacement_change_percent',100*abs(max(hypot(ux,uy))-rows(2).max_displacement_m)/rows(2).max_displacement_m, ...
    'coarse_max_core_probe_tensile_principal_stress_Pa',max(probe), ...
    'fine_max_core_probe_tensile_principal_stress_Pa',max(rows(2).core_probe_max_tensile_principal_stress_Pa), ...
    'probe_stress_change_percent',100*abs(max(probe)-max(rows(2).core_probe_max_tensile_principal_stress_Pa))/max(rows(2).core_probe_max_tensile_principal_stress_Pa));
fid=fopen(fullfile(out,'mesh_check.json'),'w','n','UTF-8');
fprintf(fid,'%s',jsonencode(check,PrettyPrint=true));fclose(fid);
disp(check);
end
