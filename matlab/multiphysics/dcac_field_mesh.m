function mesh=dcac_field_mesh(q)
% Internal verification request; ordinary application runs keep 2 mm meshes.
mesh=struct('magnetic_hmax_m',.002,'thermal_hmax_m',.002);
if ~isfield(q,'mesh'),return;end
if ~isstruct(q.mesh) || ~isscalar(q.mesh)
    error('DCAC:FieldMesh','mesh must be a scalar structure.');
end
names=fieldnames(q.mesh);
for k=1:numel(names)
    key=names{k}; value=q.mesh.(key);
    if ~isfield(mesh,key) || ~isnumeric(value) || ~isscalar(value) || ...
            ~isreal(value) || ~isfinite(value) || value<.00025 || value>.005
        error('DCAC:FieldMesh','Mesh sizes must be finite scalars between 0.25 and 5 mm.');
    end
    mesh.(key)=value;
end
end
