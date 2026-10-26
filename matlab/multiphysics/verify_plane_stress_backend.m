function report=verify_plane_stress_backend()
% Gate backend CTE handling with free-expansion and restrained benchmarks.
persistent cached
if ~isempty(cached),report=cached;return;end
nus=[.25,.30,.35]; factors=zeros(size(nus)); errors=zeros(3,3);
for k=1:numel(nus)
    nu=nus(k); candidates=[1,(1-2*nu)/(1-nu)]; accepted=false;
    for factor=candidates
        model=createpde('structural','static-planestress');
        geometryFromEdges(model,decsg([3;4;0;.05;.05;0;0;0;.03;.03]));
        generateMesh(model,'Hmax',.008,'GeometricOrder','quadratic');
        E=150e9;alpha=8e-6;dT=100;
        structuralProperties(model,'YoungsModulus',E,'PoissonsRatio',nu,'CTE',alpha*factor);
        xy=zeros(2,model.Geometry.NumVertices);
        for v=1:size(xy,2)
            ids=findNodes(model.Mesh,'region','Vertex',v);xy(:,v)=model.Mesh.Nodes(:,ids(1));
        end
        [~,left]=min(sum(xy.^2,1));[~,right]=min(sum((xy-[.05;0]).^2,1));
        structuralBC(model,'Vertex',left,'XDisplacement',0,'YDisplacement',0);
        structuralBC(model,'Vertex',right,'YDisplacement',0);
        model.ReferenceTemperature=0;structuralBodyLoad(model,'Temperature',dT);
        r=solve(model);
        uerr=max(hypot(r.Displacement.ux-alpha*dT*model.Mesh.Nodes(1,:)',r.Displacement.uy-alpha*dT*model.Mesh.Nodes(2,:)'));
        serr=max(abs([r.Stress.sxx;r.Stress.syy;r.Stress.sxy]));
        structuralBC(model,'Edge',1:model.Geometry.NumEdges,'Constraint','fixed');
        r=solve(model);exact=-E*alpha*dT/(1-nu);
        rerr=max(abs([r.Stress.sxx-exact;r.Stress.syy-exact;r.Stress.sxy]));
        if uerr<1e-10 && serr<1 && rerr<1
            factors(k)=factor;errors(k,:)=[uerr,serr,rerr];accepted=true;break;
        end
    end
    assert(accepted,'DCAC:CTE','Plane-stress analytical benchmarks failed; field solving is blocked.');
end
report=struct('status','passed','matlab_version',version,'poisson',nus,'cte_factors',factors, ...
    'errors_free_u_m_free_stress_Pa_restrained_stress_Pa',errors);
cached=report;
end
