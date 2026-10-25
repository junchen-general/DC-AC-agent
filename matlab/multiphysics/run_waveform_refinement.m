function run_waveform_refinement()
root=fileparts(mfilename('fullpath'));
for power=[500 750]
    name=sprintf('electrical_reference_400_E70FE68_%dW',power);
    r=jsondecode(fileread(fullfile(root,'outputs',name,'request.json')));
    run_electrical_reference(800,r.spec,sprintf('E70FE68_%dW',power));
end
refresh_electrical_figures;
end
