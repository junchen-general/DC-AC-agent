function run_e70_catalog_candidate()
% E70 N87 2.5 mm catalog AL screen: circuit parameters are not FE-verified.
root=fileparts(mfilename('fullpath'));
mat=jsondecode(fileread(fullfile(root,'material_assumptions.json')));
e=mat.e70_alternative_screening;
cu=mat.winding_screening;
L=e.catalog_AL_nH*1e-9*e.turns^2;
wireArea=pi*(e.assumed_equal_copper_area_solid_wire_diameter_m/2)^2;
R=cu.copper_resistivity_20C_ohm_m*e.turns*e.catalog_mean_turn_length_m/wireArea;
for nominalW=[500,750]
    updates=struct('inductance',L,'winding_resistance',R,'output_power',nominalW);
    run_electrical_reference(400,updates,sprintf('E70catalog68_%dW',nominalW));
end
end
