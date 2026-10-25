function run_e70_unit_response
% Conditional E70 thermal/structural 1 W response, not an operating result.
root=fileparts(mfilename('fullpath'));
out=fullfile(root,'outputs','unit_response_e70');
if ~isfolder(out),mkdir(out);end
cases={'winding',10,.002,'minimal';'winding',10,.0015,'minimal'; ...
    'core',10,.0015,'minimal';'winding',15,.0015,'minimal'};
rows=struct([]);
for k=1:size(cases,1)
    [m,thermal,temperature,structural,displacement]=solve_unit_e70_thermal_structural(cases{k,:});
    if k==1,rows=m;else,rows(k)=m;end
    fprintf('E70_UNIT=%d T_K_per_W=%.8g U_m_per_W=%.8g BAL=%.5g\n', ...
        k,m.peak_temperature_rise_K_per_W,m.max_displacement_m_per_W,m.heat_balance_relative_error);
    save(fullfile(out,sprintf('case_%02d.mat',k)),'m','thermal','temperature','structural','displacement','-v7.3');
    if k==2
        fig=figure('Visible','off','Color','w','Position',[50,50,1100,520]);
        subplot(1,2,1);pdeplot(thermal,'XYData',temperature.Temperature,'Contour','off');
        axis equal tight;title('E70 1 W winding loss: temperature rise (K/W)');
        xlabel('x (m)');ylabel('y (m)');
        subplot(1,2,2);pdeplot(structural,'XYData',displacement.Displacement.Magnitude*1e6,'Contour','off');
        axis equal tight;title('E70 1 W winding loss: displacement (micrometers/W)');
        xlabel('x (m)');ylabel('y (m)');colormap(parula);
        exportgraphics(fig,fullfile(out,'unit_response.png'),'Resolution',180);close(fig);
    end
end
fid=fopen(fullfile(out,'metrics.json'),'w','n','UTF-8');
fprintf(fid,'%s',jsonencode(rows,PrettyPrint=true));fclose(fid);
assert(all([rows.heat_balance_relative_error]<.01),'Heat balance failed');
end
