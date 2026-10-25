function [metrics,thermal,temperature,structural,displacement] = solve_unit_e70_thermal_structural(source,h,hmax,mount)
% CONDITIONAL unit-load response, not an operating-temperature prediction.
% Bonded, polymer-filled rectangular E70 surrogate, extruded by 32 mm.
% Front/back faces are adiabatic; convection only on the outside perimeter.
% Material values are screening assumptions except cited generic ferrite k.
arguments
    source (1,:) char {mustBeMember(source,{'winding','core'})}
    h (1,1) double {mustBePositive}
    hmax (1,1) double {mustBePositive}
    mount (1,:) char {mustBeMember(mount,{'minimal','clamped'})}
end
depth=.032; gap=.0025;
rect=@(x1,x2,y1,y2) [3;4;x1;x2;x2;x1;y1;y1;y2;y2];
gd=[rect(-.03525,.03525,-.0332,.0332),rect(-.024,-.011,-.0219,.0219), ...
    rect(.011,.024,-.0219,.0219),rect(-.011,.011,-gap/2,gap/2), ...
    rect(-.023,-.0125,-.020,.020),rect(.0125,.023,-.020,.020)];
ns=char('O','W','V','G','L','R')'; dl=decsg(gd,'O+W+V+G+L+R',ns);
outer=find(dl(6,:)==0 | dl(7,:)==0);
thermal=createpde('thermal','steadystate'); geometryFromEdges(thermal,dl);
generateMesh(thermal,'Hmax',hmax,'GeometricOrder','quadratic');
p=thermal.Mesh.Nodes; e=thermal.Mesh.Elements(1:3,:);
v1=p(:,e(1,:));v2=p(:,e(2,:));v3=p(:,e(3,:));
area=abs((v2(1,:)-v1(1,:)).*(v3(2,:)-v1(2,:))- ...
    (v3(1,:)-v1(1,:)).*(v2(2,:)-v1(2,:)))/2;
center=(v1+v2+v3)/3;
region=zeros(1,thermal.Geometry.NumFaces); faceArea=region;
for face=1:numel(region)
    ids=findElements(thermal.Mesh,'region','Face',face);
    xy=center(:,ids(1)); x=xy(1); y=xy(2);
    isCore=~(abs(x)>.011 && abs(x)<.024 && abs(y)<.0219) && ...
        ~(abs(x)<.011 && abs(y)<gap/2);
    isCoil=abs(x)>.0125 && abs(x)<.023 && abs(y)<.020;
    region(face)=1+isCore+2*isCoil; % 1 polymer; 2 ferrite; 3 winding pack
    faceArea(face)=sum(area(ids));
end
target=3; if strcmp(source,'core'),target=2;end
heatedVolume=sum(faceArea(region==target))*depth;
conductivity=[.2,5,2]; % W/(m K), winding-pack transverse effective k
for face=1:numel(region)
    thermalProperties(thermal,'Face',face,'ThermalConductivity',conductivity(region(face)));
    internalHeatSource(thermal,double(region(face)==target)/heatedVolume,'Face',face);
end
thermalBC(thermal,'Edge',outer,'ConvectionCoefficient',h,'AmbientTemperature',0);
temperature=solve(thermal);
% Energy balance: every perimeter segment is linear; sample densely.
outwardHeat=0;
for edge=outer
    x=linspace(dl(2,edge),dl(3,edge),101);
    y=linspace(dl(4,edge),dl(5,edge),101);
    values=interpolateTemperature(temperature,x,y);
    edgeLength=hypot(x(end)-x(1),y(end)-y(1));
    outwardHeat=outwardHeat+depth*h*trapz(linspace(0,edgeLength,101),values);
end
structural=createpde('structural','static-planestress');
geometryFromEdges(structural,dl);
generateMesh(structural,'Hmax',hmax,'GeometricOrder','quadratic');
% Generic ferrite E=150 GPa, CTE=8e-6/K; polymer/winding values assumed.
young=[2e9,150e9,10e9]; poisson=[.35,.25,.30]; cte=[60e-6,8e-6,17e-6];
for face=1:numel(region)
    r=region(face);
    structuralProperties(structural,'Face',face,'YoungsModulus',young(r), ...
        'PoissonsRatio',poisson(r),'CTE',plane_stress_cte_adapter(cte(r),poisson(r)));
end
if strcmp(mount,'clamped')
    bottom=find(abs(dl(4,:)+.0332)<1e-10 & abs(dl(5,:)+.0332)<1e-10);
    structuralBC(structural,'Edge',bottom,'Constraint','fixed');
else
    vertices=zeros(2,structural.Geometry.NumVertices);
    for v=1:structural.Geometry.NumVertices
        vertexNode=findNodes(structural.Mesh,'region','Vertex',v);
        vertices(:,v)=structural.Mesh.Nodes(:,vertexNode(1));
    end
    [~,left]=min(sum((vertices-[-.03525;-.0332]).^2,1));
    [~,right]=min(sum((vertices-[.03525;-.0332]).^2,1));
    structuralBC(structural,'Vertex',left,'XDisplacement',0,'YDisplacement',0);
    structuralBC(structural,'Vertex',right,'YDisplacement',0);
end
structural.ReferenceTemperature=0;
structuralBodyLoad(structural,'Temperature',temperature);
displacement=solve(structural);
probeX=[0,.029,0];probeY=[.013,0,.027];
stress=interpolateStress(displacement,probeX,probeY);
principal=.5*(stress.sxx+stress.syy)+sqrt((.5*(stress.sxx-stress.syy)).^2+stress.sxy.^2);
principal=max(principal,0); % Third principal stress is zero in plane stress.
metrics=struct('source',source,'input_power_W',1,'h_W_m2K',h, ...
    'hmax_m',hmax,'mount',mount,'nodes',size(p,2), ...
    'peak_temperature_rise_K_per_W',max(temperature.Temperature), ...
    'winding_probe_rise_K_per_W',interpolateTemperature(temperature,.018,0), ...
    'core_probe_rise_K_per_W',interpolateTemperature(temperature,0,.013), ...
    'heat_balance_relative_error',abs(outwardHeat-1), ...
    'max_displacement_m_per_W',max(displacement.Displacement.Magnitude), ...
    'core_probe_principal_stress_Pa_per_W',principal(:)', ...
    'core_probe_sxx_Pa_per_W',stress.sxx(:)', ...
    'core_probe_syy_Pa_per_W',stress.syy(:)', ...
    'core_probe_sxy_Pa_per_W',stress.sxy(:)', ...
    'probe_xy_m',[probeX;probeY], ...
    'thermal_strain_adapter','R2023bU7 plane-stress CTE adapter; physical CTE preserved in material_assumptions.json', ...
    'status','E70_unit_response_assumed_bonded_potted_geometry_not_operating_result');
end
