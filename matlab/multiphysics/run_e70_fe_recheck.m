function run_e70_fe_recheck()
% Recheck E70 candidate at 750 W with local 2-D FE L, not catalog AL.
root=fileparts(mfilename('fullpath'));
fe=jsondecode(fileread(fullfile(root,'outputs','magnetic_e70','metrics.json')));
assumptions=jsondecode(fileread(fullfile(root,'material_assumptions.json')));
e=assumptions.e70_alternative_screening;
cu=assumptions.winding_screening;
area=pi*(e.assumed_equal_copper_area_solid_wire_diameter_m/2)^2;
R=cu.copper_resistivity_20C_ohm_m*e.turns*e.catalog_mean_turn_length_m/area;
updates=struct('inductance',fe(2).L_energy_H, ...
    'winding_resistance',R,'output_power',750);
run_electrical_reference(400,updates,'E70FE68_750W');
end
