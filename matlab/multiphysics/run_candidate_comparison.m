function run_candidate_comparison()
% Same 400-subdivision ideal circuit screen for the two remaining E55 cases.
root=fileparts(mfilename('fullpath'));
mag=jsondecode(fileread(fullfile(root,'outputs','magnetic','metrics.json')));
assumptions=jsondecode(fileread(fullfile(root,'material_assumptions.json')));
rho=assumptions.winding_screening.copper_resistivity_20C_ohm_m;
meanTurn=assumptions.winding_screening.mean_turn_length_m;
diameter=assumptions.winding_screening.bare_wire_diameter_m;
wireArea=pi*(diameter/2)^2;
for id=[5,6]
    turns=mag(id).turns;
    updates=struct('inductance',mag(id).L_energy_H, ...
        'winding_resistance',rho*turns*meanTurn/wireArea);
    run_electrical_reference(400,updates,sprintf('candidate%d',turns));
end
end
