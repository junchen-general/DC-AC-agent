function effectiveCTE = plane_stress_cte_adapter(physicalCTE,poisson)
% Backend-specific adapter, NOT a change to the material's physical CTE.
% R2023b U7 internal constructFCoefficient, generateThermalBoundaryLoad,
% and StaticStructuralResults use E*CTE/(1-2*nu) for thermal stress.
% Plane stress requires E*alpha/(1-nu). Compensate consistently at input.
% Verified by free-expansion and fully-restrained analytical benchmarks.
assert(contains(version,'23.2.0.2515942'), ...
    'This adapter is verified only on MATLAB R2023b Update 7; revalidate on other releases.');
effectiveCTE=physicalCTE.*(1-2*poisson)./(1-poisson);
end
