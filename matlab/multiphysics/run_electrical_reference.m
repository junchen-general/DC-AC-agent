function run_electrical_reference(timeSubdivisions,specUpdates,caseTag)
% Local reproduction of upstream baseline; not a B-approved handoff.
root = fileparts(mfilename('fullpath'));
if nargin<1,timeSubdivisions=100;end
if nargin<2,specUpdates=struct;end
if nargin<3,caseTag='';end
addpath(fullfile(root,'compatibility'));
spec = struct('input_voltage',380,'output_voltage',220,'output_power',500, ...
    'output_frequency',50,'switching_frequency',20000,'inductance',0.002, ...
    'capacitance',4.7e-6,'winding_resistance',0.25,'stop_time',0.24, ...
    'load_step',false,'load_step_time',0.12,'load_final_ratio',0.5);
names=fieldnames(specUpdates);
for k=1:numel(names)
    assert(isfield(spec,names{k}),'Unknown electrical parameter');
    spec.(names{k})=specUpdates.(names{k});
end
out = fullfile(root,'outputs','electrical_reference');
if timeSubdivisions~=100, out=[out,'_',num2str(timeSubdivisions)];end
if ~isempty(caseTag),out=[out,'_',caseTag];end
if ~isfolder(out), mkdir(out); end
request = struct('action','simulate','spec',spec,'output_dir',out);
fid = fopen(fullfile(out,'request.json'),'w','n','UTF-8');
fprintf(fid,'%s',jsonencode(request)); fclose(fid);
dcac_execute(fullfile(out,'request.json'),timeSubdivisions);
d = load(fullfile(out,'simulation.mat'));
report = jsondecode(fileread(fullfile(out,'result.json')));
report.provenance = struct('status','local_upstream_reproduction_not_B_approved', ...
    'source_blob_sha','95e8af6ae07d6abdb75505c292cc45e3bc754c62', ...
    'source_url','https://github.com/junchen-general/DC-AC-agent/blob/main/matlab/dcac_execute.m', ...
    'run_id',['C-local-electrical-reference-',num2str(timeSubdivisions),'-',caseTag], ...
    'design_revision','upstream-defaults-2026-10-23', ...
    'time_subdivisions',timeSubdivisions, ...
    'compatibility_patch','Display colors; min(x,1) replaced by (x+1-abs(x-1))/2; explicit time subdivision argument, default 100');
report.provenance.spec_updates=specUpdates;
report.provenance.case_tag=caseTag;
report.full_run_peak_A = max(abs(d.y(:,2)));
[~,peakIndex] = max(abs(d.y(:,2)));
report.full_run_peak_time_s = d.t(peakIndex);
report.csv_columns = {'time_s','vout_V','inductor_current_A','load_current_A','vbridge_V'};
fid = fopen(fullfile(out,'handoff_local.json'),'w','n','UTF-8');
fprintf(fid,'%s',jsonencode(report,PrettyPrint=true)); fclose(fid);
disp(report.metrics); fprintf('FULL_RUN_PEAK_A=%.9g\n',report.full_run_peak_A);
end
