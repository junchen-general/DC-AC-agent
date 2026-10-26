function dcac_multiphysics(requestPath)
% One-way E70 candidate field analysis from an identified electrical run.
out=fileparts(requestPath); phase='read_request'; totalClock=tic;
try
    q=jsondecode(fileread(requestPath)); o=q.options; mesh=dcac_field_mesh(q);
    phase='validate_electrical';
    parent=jsondecode(fileread(fullfile(q.parent_dir,'result.json')));
    assert(parent.ok && strcmp(parent.source,'MATLAB/Simulink') && strcmp(parent.action,'simulate'),'A real electrical simulation is required.');
    assert(isequaln(orderfields(parent.spec),orderfields(q.spec)),'Electrical spec mismatch.');
    raw=load(fullfile(q.parent_dir,'electrical_raw_v1.mat'),'t','s','meta','signals','context');
    assert(isequaln(orderfields(raw.s),orderfields(q.spec)),'Raw spec mismatch.');
    assert(strcmp(raw.meta.data_origin,'real_simulation') && raw.meta.sampling.decimation==1,'Full-resolution simulation data required.');
    assert(strcmp(raw.context.session_id,q.session_id) && strcmp(raw.context.run_id,q.parent_run_id) && raw.context.design_revision==q.revision,'Raw identity mismatch.');
    t=raw.t(:); il=raw.signals.i_inductor_A(:);dt=median(diff(t));
    assert(numel(t)==numel(il) && all(isfinite(t)) && all(isfinite(il)) && all(diff(t)>0),'Invalid current waveform.');
    assert(max(abs(diff(t)-dt))/dt<1e-6,'Nonuniform sampling.');
    select=t>=t(end)-4/q.spec.output_frequency-.1*dt & t<t(end)-.1*dt;
    assert(sum(select)==round(4/q.spec.output_frequency/dt),'Incomplete final four-cycle window.');
    irms=sqrt(mean(il(select).^2));ipeak=max(abs(il(select))); assert(ipeak>0,'Zero excitation.');
    phase='verify_structural_backend'; bench=verify_plane_stress_backend();
    phase='magnetic'; magClock=tic;
    [mag,magModel,magSolution]=solve_magnetic_e70(.0025,68,mesh.magnetic_hmax_m,.08,ipeak,2200);
    magneticSeconds=toc(magClock);
    assert(mag.energy_identity_relative_error<.01,'Magnetic energy identity failed.');
    mag.input_status='parent_run_final_four_cycle_current_peak';
    phase='thermal_structural'; thermalClock=tic;
    [mw,tw,rw,sw,dw]=solve_unit_e70_thermal_structural('winding',o.convection_w_m2k,mesh.thermal_hmax_m,'minimal');
    [mc,tc,rc,sc,dc]=solve_unit_e70_thermal_structural('core',o.convection_w_m2k,mesh.thermal_hmax_m,'minimal');
    thermalStructuralSeconds=toc(thermalClock);
    assert(isequal(tw.Mesh.Nodes,tc.Mesh.Nodes) && isequal(tw.Mesh.Elements,tc.Mesh.Elements),'Thermal mesh mismatch.');
    assert(isequal(sw.Mesh.Nodes,sc.Mesh.Nodes) && isequal(sw.Mesh.Elements,sc.Mesh.Elements),'Structural mesh mismatch.');
    assert(max([mw.heat_balance_relative_error,mc.heat_balance_relative_error])<.02,'Heat balance failed.');
    r20=1.724e-8*68*.209/(64*pi*(.00015/2)^2); p20=irms^2*r20; alpha=.00393;
    peak=o.ambient_c; converged=false;
    for iteration=1:200
        pdc=p20*(1+alpha*(peak-20)); pw=pdc+o.extra_winding_heat_w; pc=o.core_heat_w;
        rise=pw*rw.Temperature+pc*rc.Temperature;
        next=o.ambient_c+max(rise);
        assert(isfinite(next) && next<1000,'Thermal feedback diverged or exceeded model scope.');
        if abs(next-peak)<1e-7,converged=true;peak=next;break;end
        peak=next;
    end
    assert(converged,'Copper-temperature feedback did not converge.');
    ux=pw*dw.Displacement.ux+pc*dc.Displacement.ux;uy=pw*dw.Displacement.uy+pc*dc.Displacement.uy;
    umag=hypot(ux,uy);sx=pw*dw.Stress.sxx+pc*dc.Stress.sxx;sy=pw*dw.Stress.syy+pc*dc.Stress.syy;sxy=pw*dw.Stress.sxy+pc*dc.Stress.sxy;
    s1=max(.5*(sx+sy)+hypot(.5*(sx-sy),sxy),0);
    aw=interpolateStress(dw,[0,.029,0],[.013,0,.027]);ac=interpolateStress(dc,[0,.029,0],[.013,0,.027]);
    px=pw*aw.sxx+pc*ac.sxx;py=pw*aw.syy+pc*ac.syy;pxy=pw*aw.sxy+pc*ac.sxy;
    probe=max(.5*(px+py)+hypot(.5*(px-py),pxy),0);
    phase='export';
    B=hypot(magSolution.XGradients,magSolution.YGradients);
    plotField(magModel,B,'Magnetic flux density (T; linear E70 candidate)',fullfile(out,'magnetic.png'));
    plotField(tw,o.ambient_c+rise,'Temperature (deg C; specified heat sources)',fullfile(out,'thermal.png'));
    plotField(sw,s1/1e6,'Tensile principal stress (MPa; corner peaks mesh-sensitive)',fullfile(out,'structural.png'));
    plotField(sw,umag*1e6,'Displacement (micrometers)',fullfile(out,'displacement.png'));
    meshEvidence=struct('configuration',mesh,'magnetic',meshStats(magModel.Mesh), ...
        'thermal',meshStats(tw.Mesh),'structural',meshStats(sw.Mesh), ...
        'magnetic_seconds',magneticSeconds,'thermal_structural_seconds',thermalStructuralSeconds);
    save(fullfile(out,'fields.mat'),'mag','magModel','magSolution','mw','mc','tw','sw','rise','ux','uy','s1','probe','bench','q', ...
        'rw','rc','dw','dc','irms','ipeak','meshEvidence','-v7.3');
    result=struct('ok',true,'status','completed','schema_version','1.0','session_id',q.session_id, ...
        'parent_run_id',q.parent_run_id,'revision',q.revision,'evidence','numerical', ...
        'component_version','E70-N87-68turn-gap2p5mm-v1','material_version','c-research-materials/0.1', ...
        'boundary_version','E70-minimal-support-adiabatic-front-back-v1', ...
        'solver',struct('name','MATLAB PDE Toolbox','version',version,'coupling','one_way_prescribed_current_conditional_candidate'), ...
        'verification',struct('plane_stress_backend',bench,'magnetic_energy_error',mag.energy_identity_relative_error, ...
            'heat_balance_error',max([mw.heat_balance_relative_error,mc.heat_balance_relative_error]), ...
            'thermal_feedback_iterations',iteration,'mesh',meshEvidence,'elapsed_seconds',toc(totalClock), ...
            'mesh_convergence','not_checked_for_this_run','electrical_step_convergence','not_checked'), ...
        'input_summary',struct('inductor_rms_A',irms,'inductor_peak_A',ipeak,'sample_time_s',dt,'window_start_s',t(end)-4/q.spec.output_frequency, ...
            'window_end_exclusive_s',t(end),'sample_count',sum(select),'options',o,'candidate_R20_ohm',r20, ...
            'circuit_L_H',q.spec.inductance,'circuit_R_ohm',q.spec.winding_resistance, ...
            'candidate_L_H',mag.L_energy_H,'L_difference_percent',100*(mag.L_energy_H/q.spec.inductance-1), ...
            'R_difference_percent',100*(r20/max(q.spec.winding_resistance,eps)-1)), ...
        'limitations',{{'E70 candidate driven by parent current; L/R not fed back to electrical simulation.', ...
            'Linear magnetic material; no saturation, hysteresis or calibrated core-loss prediction.', ...
            'Extra winding heat and core heat are prescribed assumptions, not predicted losses.', ...
            'Thermal steady state and linear plane stress; ideal bonded assembly, no contact or magnetic force.', ...
            'Stress probes are screening values; corner maxima are mesh-sensitive, no strength safety factor.', ...
            'This run has no mesh or electrical time-step convergence certification.'}});
    result.domains.magnetic=struct('status','completed','metrics',struct('candidate_inductance',metric(mag.L_energy_H,'H'), ...
        'bulk_peak_flux_density',metric(mag.bulk_center_leg_B_T,'T')),'artifacts',{{'magnetic.png','fields.mat'}});
    result.domains.thermal=struct('status','completed','metrics',struct('peak_temperature',metric(peak,'degC'), ...
        'candidate_dc_copper_heat',metric(pdc,'W'),'specified_core_heat',metric(pc,'W'), ...
        'specified_extra_winding_heat',metric(o.extra_winding_heat_w,'W')),'artifacts',{{'thermal.png'}});
    result.domains.structural=struct('status','completed','metrics',struct('max_displacement',metric(max(umag),'m'), ...
        'core_probe_tensile_stress',metric(max(probe),'Pa'), ...
        'corner_sensitive_max_tensile_stress',metric(max(s1),'Pa')),'artifacts',{{'structural.png','displacement.png'}});
    writeJson(fullfile(out,'result.json'),result);fprintf('DCAC_FIELDS_SUCCESS\n');
catch err
    writeJson(fullfile(out,'result.json'),struct('ok',false,'phase',phase,'error',err.message,'report',getReport(err,'extended','hyperlinks','off')));
    fprintf(2,'%s\n',err.message);
end
end
function info=meshStats(mesh)
p=mesh.Nodes; e=mesh.Elements(1:3,:);
a=p(:,e(2,:))-p(:,e(1,:)); b=p(:,e(3,:))-p(:,e(1,:));
area=abs(a(1,:).*b(2,:)-a(2,:).*b(1,:))/2;
quality=4*sqrt(3)*area./(sum(a.^2,1)+sum(b.^2,1)+sum((a-b).^2,1));
info=struct('nodes',size(p,2),'triangles',size(e,2),'minimum_quality',min(quality), ...
    'median_quality',median(quality),'quality_definition','4*sqrt(3)*area/sum(corner_edge_length^2)');
end
function m=metric(value,unit)
assert(isscalar(value)&&isfinite(value),'Nonfinite metric');m=struct('value',value,'unit',unit);
end
function writeJson(path,data)
fid=fopen(path,'w','n','UTF-8');assert(fid>=0);clean=onCleanup(@()fclose(fid));fprintf(fid,'%s',jsonencode(data,PrettyPrint=true));
end
function plotField(model,values,titleText,path)
f=figure('Visible','off','Color','w','Position',[50,50,900,650]);clean=onCleanup(@()close(f));
pdeplot(model,'XYData',values,'Contour','off');axis equal tight;title(titleText);xlabel('x (m)');ylabel('y (m)');colormap(parula);exportgraphics(f,path,'Resolution',130);
end
