function test_field_mesh()
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
addpath(fullfile(root,'matlab','multiphysics'));
c=dcac_field_mesh(struct());
assert(c.magnetic_hmax_m==.002 && c.thermal_hmax_m==.002);
c=dcac_field_mesh(struct('mesh',struct('magnetic_hmax_m',.001,'thermal_hmax_m',.001)));
assert(c.magnetic_hmax_m==.001 && c.thermal_hmax_m==.001);
bad={NaN,0,-.001,.02,true,[.001,.002]};
for k=1:numel(bad)
    failed=false;
    try
        dcac_field_mesh(struct('mesh',struct('magnetic_hmax_m',bad{k})));
    catch err
        failed=strcmp(err.identifier,'DCAC:FieldMesh');
    end
    assert(failed,'Invalid mesh size was accepted.');
end
failed=false;
try,dcac_field_mesh(struct('mesh',struct('unexpected',1)));
catch err,failed=strcmp(err.identifier,'DCAC:FieldMesh');end
assert(failed,'Unknown mesh field was accepted.');
disp('FIELD_MESH_VALIDATION_PASS');
end
