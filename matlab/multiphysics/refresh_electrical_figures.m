function refresh_electrical_figures()
root=fileparts(mfilename('fullpath'));
addpath(fullfile(root,'compatibility'));
folders=dir(fullfile(root,'outputs','electrical_reference*'));
for k=1:numel(folders)
    folder=fullfile(folders(k).folder,folders(k).name);
    if ~isfile(fullfile(folder,'simulation.mat')),continue;end
    d=load(fullfile(folder,'simulation.mat'));
    r=jsondecode(fileread(fullfile(folder,'result.json')));
    render_dcac_waveforms(d.t,d.y,d.s,r.metrics,folder);
    fprintf('REFRESHED %s\n',folders(k).name);
end
end
