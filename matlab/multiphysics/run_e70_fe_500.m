function run_e70_fe_500()
% Same E70 FE-derived L and copper R as the 750 W course scenario.
root=fileparts(mfilename('fullpath'));
fe=jsondecode(fileread(fullfile(root,'outputs','magnetic_e70','metrics.json')));
a=jsondecode(fileread(fullfile(root,'material_assumptions.json')));
e=a.e70_alternative_screening;
cu=a.winding_screening;
area=e.selected_strand_count*pi*(e.selected_strand_bare_diameter_m/2)^2;
R=cu.copper_resistivity_20C_ohm_m*e.turns*e.catalog_mean_turn_length_m/area;
updates=struct('inductance',fe(2).L_energy_H,'winding_resistance',R,'output_power',500);
run_electrical_reference(400,updates,'E70FE68_500W');
end
