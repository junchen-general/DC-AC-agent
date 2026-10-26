function effectiveCTE=plane_stress_cte_adapter(physicalCTE,poisson)
% Physical CTE unchanged; backend correction is analytically verified.
report=verify_plane_stress_backend();
idx=find(abs(report.poisson-poisson)<1e-12,1);
assert(~isempty(idx),'Unverified Poisson ratio in plane-stress adapter.');
effectiveCTE=physicalCTE.*report.cte_factors(idx);
end
