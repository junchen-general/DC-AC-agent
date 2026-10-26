function dcac_heat_sensitivity(fieldFile,out)
% Recombine real unit-load FE solutions; solve the copper feedback each time.
a=load(fieldFile,'rw','rc','dw','dc','irms','q');
if ~exist(out,'dir'),mkdir(out);end
r20=1.724e-8*68*.209/(64*pi*(.00015/2)^2);p20=a.irms^2*r20;
aw=interpolateStress(a.dw,[0,.029,0],[.013,0,.027]);
ac=interpolateStress(a.dc,[0,.029,0],[.013,0,.027]);
rows={};n=0;levels=[0,.5,1];
for extra=levels
    for core=levels
        peak=a.q.options.ambient_c;converged=false;
        for iteration=1:200
            pdc=p20*(1+.00393*(peak-20));pw=pdc+extra;
            next=a.q.options.ambient_c+max(pw*a.rw.Temperature+core*a.rc.Temperature);
            assert(isfinite(next)&&next<1000,'Thermal feedback diverged.');
            if abs(next-peak)<1e-7,peak=next;converged=true;break;end
            peak=next;
        end
        assert(converged,'Thermal feedback did not converge.');
        ux=pw*a.dw.Displacement.ux+core*a.dc.Displacement.ux;
        uy=pw*a.dw.Displacement.uy+core*a.dc.Displacement.uy;
        sx=pw*aw.sxx+core*ac.sxx;sy=pw*aw.syy+core*ac.syy;sxy=pw*aw.sxy+core*ac.sxy;
        stress=max(.5*(sx+sy)+hypot(.5*(sx-sy),sxy),0);
        n=n+1;rows{n}=struct('extra_winding_heat_W',extra,'core_heat_W',core, ...
            'peak_temperature_C',peak,'dc_copper_heat_W',pdc,'iterations',iteration, ...
            'max_displacement_um',1e6*max(hypot(ux,uy)), ...
            'core_probe_tensile_stress_MPa',max(stress)/1e6);
    end
end
rows=[rows{:}];
parent=jsondecode(fileread(fullfile(fileparts(fieldFile),'result.json')));
baseline=rows([rows.extra_winding_heat_W]==.5 & [rows.core_heat_W]==.5);
assert(abs(baseline.peak_temperature_C-parent.domains.thermal.metrics.peak_temperature.value)<1e-6);
assert(abs(baseline.max_displacement_um-1e6*parent.domains.structural.metrics.max_displacement.value)<1e-6);
result=struct('ok',true,'status','completed','evidence','numerical_unit_response_recombination', ...
    'method','Linear FE unit responses reused; copper-temperature feedback recomputed per case', ...
    'inductor_rms_A',a.irms,'ambient_C',a.q.options.ambient_c, ...
    'convection_W_m2K',a.q.options.convection_w_m2k,'rows',rows);
for file={'sensitivity.json','result.json'}
    fid=fopen(fullfile(out,file{1}),'w','n','UTF-8');
    assert(fid>=0);fprintf(fid,'%s',jsonencode(result,PrettyPrint=true));fclose(fid);
end
f=figure('Visible','off','Color','w','Position',[50,50,1250,380]);cleanup=onCleanup(@()close(f));
tiledlayout(1,3,'Padding','compact');
fields={'peak_temperature_C','max_displacement_um','core_probe_tensile_stress_MPa'};
titles={'Peak temperature (deg C)','Maximum displacement (um)','Core probe tensile stress (MPa)'};
for k=1:3
    nexttile;values=reshape([rows.(fields{k})],3,3);
    imagesc(levels,levels,values);set(gca,'YDir','normal','XTick',levels,'YTick',levels);axis square;colorbar;colormap(parula);
    xlabel('Extra winding heat (W)');ylabel('Core heat (W)');title(titles{k});
end
exportgraphics(f,fullfile(out,'sensitivity.png'),'Resolution',150);
fprintf('HEAT_SENSITIVITY_PASS\n');
end
