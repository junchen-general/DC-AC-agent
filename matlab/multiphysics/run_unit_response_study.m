function run_unit_response_study
root=fileparts(mfilename('fullpath'));out=fullfile(root,'outputs','unit_response');
if ~isfolder(out),mkdir(out);end
cases={'winding',10,.002,'minimal'; 'winding',10,.0012,'minimal'; ...
    'core',10,.0012,'minimal';'winding',5,.0012,'minimal'; ...
    'winding',15,.0012,'minimal';'winding',10,.0012,'clamped'; ...
    'winding',10,.0008,'minimal'};
for k=1:size(cases,1)
    [m,thermal,temperature,structural,displacement]=solve_unit_thermal_structural(cases{k,:});
    if k==1,rows=m;else,rows(k)=m;end
    fprintf('UNIT_CASE=%d TMAX_K_PER_W=%.8g DISP_m_PER_W=%.8g BALANCE_ERROR=%.5g\n', ...
        k,m.peak_temperature_rise_K_per_W,m.max_displacement_m_per_W,m.heat_balance_relative_error);
    save(fullfile(out,sprintf('case_%02d.mat',k)),'m','thermal','temperature','structural','displacement','-v7.3');
    if k==2
        fig=figure('Visible','off','Color','w','Position',[100,100,1100,520]);
        subplot(1,2,1);pdeplot(thermal,'XYData',temperature.Temperature,'Contour','off');
        axis equal tight;title('Unit winding loss: temperature rise (K/W)');xlabel('x (m)');ylabel('y (m)');
        subplot(1,2,2);pdeplot(structural,'XYData',displacement.Displacement.Magnitude*1e6,'Contour','off');
        axis equal tight;title('Unit winding loss: displacement (micrometers/W)');xlabel('x (m)');ylabel('y (m)');
        colormap(parula);exportgraphics(fig,fullfile(out,'unit_response.png'),'Resolution',180);close(fig);
    end
end
fid=fopen(fullfile(out,'metrics.json'),'w','n','UTF-8');fprintf(fid,'%s',jsonencode(rows,PrettyPrint=true));fclose(fid);
assert(all([rows.heat_balance_relative_error]<.01),'Heat balance failed');
fprintf('UNIT_RESPONSE_STUDY_COMPLETE\n');
end
