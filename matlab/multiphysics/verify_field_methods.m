function verify_field_methods
% Independent numerical checks, not performance results of the inductor.
root=fileparts(mfilename('fullpath'));out=fullfile(root,'outputs','verification');
if ~isfolder(out),mkdir(out);end
[m1,~,~]=solve_magnetic_section(.0015,74,.004,.07,1,2200);
[m2,~,~]=solve_magnetic_section(.0015,74,.004,.07,2,2200);
assert(abs(m1.L_energy_H/m2.L_energy_H-1)<1e-10,'Linear inductance scaling failed');
assert(abs(m2.bulk_center_leg_B_T/m1.bulk_center_leg_B_T-2)<1e-10,'Flux scaling failed');
% Free homogeneous expansion must not generate artificial thermal stress.
s=createpde('structural','static-planestress');
gd=[3;4;0;.05;.05;0;0;0;.03;.03];
geometryFromEdges(s,decsg(gd));
generateMesh(s,'Hmax',.004,'GeometricOrder','quadratic');
structuralProperties(s,'YoungsModulus',150e9,'PoissonsRatio',.25,'CTE',8e-6);
vertices=zeros(2,s.Geometry.NumVertices);
for v=1:s.Geometry.NumVertices
    idx=findNodes(s.Mesh,'region','Vertex',v);vertices(:,v)=s.Mesh.Nodes(:,idx(1));
end
[~,left]=min(sum(vertices.^2,1));
[~,right]=min(sum((vertices-[.05;0]).^2,1));
structuralBC(s,'Vertex',left,'XDisplacement',0,'YDisplacement',0);
structuralBC(s,'Vertex',right,'YDisplacement',0);
s.ReferenceTemperature=0;structuralBodyLoad(s,'Temperature',100);
r=solve(s);
exactX=8e-6*100*s.Mesh.Nodes(1,:)'; exactY=8e-6*100*s.Mesh.Nodes(2,:)';
maxError=max(hypot(r.Displacement.ux-exactX,r.Displacement.uy-exactY));
maxStress=max(abs([r.Stress.sxx;r.Stress.syy;r.Stress.sxy]));
fprintf('FREE_EXPANSION_ERROR=%.12g MAX_STRESS=%.12g MAX_UX=%.12g MAX_UY=%.12g\n', ...
    maxError,maxStress,max(r.Displacement.ux),max(r.Displacement.uy));
save(fullfile(out,'free_expansion_diagnostic.mat'),'s','r','vertices','left','right','maxError','maxStress');
rawMaxError=maxError;
structuralProperties(s,'YoungsModulus',150e9,'PoissonsRatio',.25, ...
    'CTE',plane_stress_cte_adapter(8e-6,.25));
r=solve(s);
maxError=max(hypot(r.Displacement.ux-exactX,r.Displacement.uy-exactY));
maxStress=max(abs([r.Stress.sxx;r.Stress.syy;r.Stress.sxy]));
assert(maxError<1e-10,'Free expansion displacement mismatch');
assert(maxStress<1,'Spurious stress in free expansion');
structuralBC(s,'Edge',1:s.Geometry.NumEdges,'Constraint','fixed');
restrained=solve(s); expected=-150e9*8e-6*100/(1-.25);
restrainedError=max(abs([restrained.Stress.sxx-expected;restrained.Stress.syy-expected;restrained.Stress.sxy]));
assert(restrainedError<1,'Fully restrained thermal stress mismatch');
metrics=struct('linear_L_scaling_relative_error',abs(m1.L_energy_H/m2.L_energy_H-1), ...
    'linear_B_scaling_error',abs(m2.bulk_center_leg_B_T/m1.bulk_center_leg_B_T-2), ...
    'free_expansion_max_displacement_error_m',maxError, ...
    'free_expansion_max_stress_Pa',maxStress, ...
    'uncorrected_backend_free_expansion_error_m',rawMaxError, ...
    'fully_restrained_stress_error_Pa',restrainedError,'status','passed');
fid=fopen(fullfile(out,'metrics.json'),'w','n','UTF-8');fprintf(fid,'%s',jsonencode(metrics,PrettyPrint=true));fclose(fid);
disp(metrics);fprintf('FIELD_METHOD_VERIFICATION_PASS\n');
end
