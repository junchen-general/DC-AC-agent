function m=run_e70_core_mesh_check()
% Independent coarse-grid core-source check for the combined scenario.
root=fileparts(mfilename('fullpath'));
[m,thermal,temperature,structural,displacement]=solve_unit_e70_thermal_structural('core',10,.002,'minimal');
out=fullfile(root,'outputs','unit_response_e70');
save(fullfile(out,'core_h10_coarse.mat'),'m','thermal','temperature','structural','displacement','-v7.3');
fid=fopen(fullfile(out,'core_h10_coarse.json'),'w','n','UTF-8');
fprintf(fid,'%s',jsonencode(m,PrettyPrint=true));fclose(fid);
disp(m);
end
