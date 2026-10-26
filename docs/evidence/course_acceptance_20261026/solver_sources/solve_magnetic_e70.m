function [metrics, model, solution] = solve_magnetic_e70(gap,turns,hmax,airHalfSize,current,muR)
% 2-D planar E70/33/32 nominal drawing, one effective center-leg gap.
% This linear model does not predict saturation or hysteresis/core losses.
arguments
    gap (1,1) double {mustBePositive}
    turns (1,1) double {mustBePositive}
    hmax (1,1) double {mustBePositive}
    airHalfSize (1,1) double {mustBePositive}
    current (1,1) double {mustBePositive} = 1
    muR (1,1) double {mustBePositive} = 2200
end
mu0 = 4*pi*1e-7;
depth = 0.032;
coilArea = 0.0105*0.040;
% TDK drawing: outer 70.5 x (2*33.2) mm; center 22 mm, between outer
% leg inner edges 48 mm, window height 21.9 mm per half. Rectangularized.
rect = @(x1,x2,y1,y2) [3;4;x1;x2;x2;x1;y1;y1;y2;y2];
gd = [rect(-airHalfSize,airHalfSize,-airHalfSize,airHalfSize), ...
    rect(-.03525,.03525,-.0332,.0332), ...
    rect(-.024,-.011,-.0219,.0219), ...
    rect(.011,.024,-.0219,.0219), ...
    rect(-.011,.011,-gap/2,gap/2), ...
    rect(-.023,-.0125,-.020,.020), ...
    rect(.0125,.023,-.020,.020)];
ns = char('A','O','W','V','G','L','R')';
dl = decsg(gd,'A+O+W+V+G+L+R',ns);
model = createpde(1);
geometryFromEdges(model,dl);
outerEdges = find(dl(6,:)==0 | dl(7,:)==0);
applyBoundaryCondition(model,'dirichlet','Edge',outerEdges,'u',0);
% Resolve the gap explicitly, without imposing a fine mesh on all far air.
gapEdges = find(abs(dl(2,:))<=.011+eps & abs(dl(3,:))<=.011+eps & ...
    abs(dl(4,:))<=gap/2+eps & abs(dl(5,:))<=gap/2+eps);
generateMesh(model,'Hmax',hmax,'Hedge',{gapEdges,min(gap/4,hmax/2)}, ...
    'GeometricOrder','quadratic');
nodes = model.Mesh.Nodes;
tri = model.Mesh.Elements(1:3,:);
centers = (nodes(:,tri(1,:))+nodes(:,tri(2,:))+nodes(:,tri(3,:)))/3;
mu = mu0*ones(1,size(tri,2));
j = zeros(1,size(tri,2));
coreElements = false(1,size(tri,2));
for face = 1:model.Geometry.NumFaces
    ids = findElements(model.Mesh,'region','Face',face);
    p = centers(:,ids(1)); x = p(1); y = p(2);
    isCore = abs(x)<.03525 && abs(y)<.0332 && ...
        ~(abs(x)>.011 && abs(x)<.024 && abs(y)<.0219) && ...
        ~(abs(x)<.011 && abs(y)<gap/2);
    thisMu = mu0*(1+(muR-1)*isCore);
    thisJ = 0;
    if abs(x)>.0125 && abs(x)<.023 && abs(y)<.020
        thisJ = -sign(x)*turns*current/coilArea;
    end
    specifyCoefficients(model,'m',0,'d',0,'c',1/thisMu,'a',0,'f',thisJ,'Face',face);
    mu(ids) = thisMu; j(ids) = thisJ; coreElements(ids) = isCore;
end
solution = solvepde(model);
% Three-point Gaussian triangle rule: integrates quadratic energy density.
v1 = nodes(:,tri(1,:)); v2 = nodes(:,tri(2,:)); v3 = nodes(:,tri(3,:));
area = abs((v2(1,:)-v1(1,:)).*(v3(2,:)-v1(2,:))- ...
    (v3(1,:)-v1(1,:)).*(v2(2,:)-v1(2,:)))/2;
b2 = zeros(size(area)); ja = zeros(size(area));
signedDoubleArea = (v2(1,:)-v1(1,:)).*(v3(2,:)-v1(2,:))- ...
    (v3(1,:)-v1(1,:)).*(v2(2,:)-v1(2,:));
g1 = [v2(2,:)-v3(2,:);v3(1,:)-v2(1,:)]./signedDoubleArea;
g2 = [v3(2,:)-v1(2,:);v1(1,:)-v3(1,:)]./signedDoubleArea;
g3 = [v1(2,:)-v2(2,:);v2(1,:)-v1(1,:)]./signedDoubleArea;
ue = solution.NodalSolution(model.Mesh.Elements);
for k=1:3
    bary = ones(1,3)/6; bary(k)=2/3;
    % Use element-local gradients. Recovered nodal gradients smear the
    % permeability-interface discontinuity and corrupt magnetic energy.
    gradA = g1.*((4*bary(1)-1)*ue(1,:)) + ...
        g2.*((4*bary(2)-1)*ue(2,:)) + g3.*((4*bary(3)-1)*ue(3,:)) + ...
        4*(bary(1)*g2+bary(2)*g1).*ue(4,:) + ...
        4*(bary(2)*g3+bary(3)*g2).*ue(5,:) + ...
        4*(bary(3)*g1+bary(1)*g3).*ue(6,:);
    shape = [bary.*(2*bary-1),4*bary(1)*bary(2), ...
        4*bary(2)*bary(3),4*bary(3)*bary(1)];
    aq = shape*ue;
    b2 = b2+sum(gradA.^2,1)/3;
    ja = ja+j.*aq/3;
end
energy = depth*sum(area.*b2./mu)/2;
sourceEnergy = depth*sum(area.*ja)/2;
% Bulk center-leg flux sampled away from gap and corner singularities.
xLine = linspace(-.009,.009,101); yLine = .013*ones(size(xLine));
[gx,~] = evaluateGradient(solution,xLine,yLine);
bulkB = abs(trapz(xLine,gx)/(xLine(end)-xLine(1)));
metrics = struct('gap_m',gap,'turns',turns,'hmax_m',hmax, ...
    'air_half_size_m',airHalfSize,'current_A',current,'mu_r',muR, ...
    'depth_m',depth,'nodes',size(nodes,2),'triangles',size(tri,2), ...
    'L_energy_H',2*energy/current^2,'L_source_H',2*sourceEnergy/current^2, ...
    'energy_identity_relative_error',abs(energy-sourceEnergy)/sourceEnergy, ...
    'bulk_center_leg_B_T',bulkB,'core_quadrature_B_rms_T', ...
    sqrt(sum(area(coreElements).*b2(coreElements))/sum(area(coreElements))), ...
    'net_excitation_A',sum(area.*j),'model','linear_2D_rectangularized_E70_33_32', ...
    'input_status','prescribed_current_not_coupled_electrical_run');
end
