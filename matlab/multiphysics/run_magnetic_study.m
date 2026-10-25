function run_magnetic_study
root = fileparts(mfilename('fullpath'));
out = fullfile(root,'outputs','magnetic');
if ~isfolder(out), mkdir(out); end
rows = struct([]);
% Three mesh sizes; local air-gap resolution is independently enforced.
cases = [.0015,74,.003,.10; .0015,74,.002,.10; .0015,74,.0012,.10; ...
         .0015,74,.0012,.15; .001,64,.0012,.10; .002,83,.0012,.10];
for k=1:size(cases,1)
    [m,model,solution] = solve_magnetic_section(cases(k,1),cases(k,2), ...
        cases(k,3),cases(k,4),1,2200);
    if k==1, rows=m; else, rows(k)=m; end
    fprintf('CASE=%d NODES=%d L_mH=%.9g B_per_A=%.9g ENERGY_ERROR=%.4g\n', ...
        k,m.nodes,m.L_energy_H*1e3,m.bulk_center_leg_B_T,m.energy_identity_relative_error);
    save(fullfile(out,sprintf('case_%02d.mat',k)),'model','solution','m','-v7.3');
    if k==3
        fig = figure('Visible','off','Color','w','Position',[100,100,1200,520]);
        subplot(1,2,1); pdegplot(model,'FaceLabels','on'); axis equal;
        xlim([-.035,.035]); ylim([-.035,.035]); xlabel('x (m)'); ylabel('y (m)');
        title('Rectangularized E55 section and face IDs');
        [bx,by] = evaluateGradient(solution);
        subplot(1,2,2); pdeplot(model,'XYData',hypot(bx,by),'Contour','off');
        axis equal; xlim([-.035,.035]); ylim([-.035,.035]);
        xlabel('x (m)'); ylabel('y (m)'); colormap(parula); cb=colorbar; cb.Label.String='|B| (T)';
        title('Linear magnetostatics at prescribed 1 A');
        exportgraphics(fig,fullfile(out,'magnetic_section.png'),'Resolution',180); close(fig);
    end
end
fid=fopen(fullfile(out,'metrics.json'),'w','n','UTF-8');
fprintf(fid,'%s',jsonencode(rows,PrettyPrint=true)); fclose(fid);
assert(all([rows.energy_identity_relative_error]<.01),'Energy identity failed.');
assert(all(abs([rows.net_excitation_A])<1e-6),'Current balance failed.');
fprintf('MAGNETIC_STUDY_COMPLETE\n');
end
