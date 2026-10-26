function comparisons=dcac_compare_step_runs(rows)
% Original thresholds retained; missing/failed runs are explicitly incomplete.
comparisons=struct([]);
stages=unique({rows.stage});scenarios=unique({rows.scenario});
for a=1:numel(stages)
    for b=1:numel(scenarios)
        pair=rows(strcmp({rows.stage},stages{a}) & strcmp({rows.scenario},scenarios{b}));
        if isempty(pair),continue;end
        [~,order]=sort([pair.steps_per_switching_period]);pair=pair(order);
        c=struct('stage',stages{a},'scenario',scenarios{b},'coarse_steps',pair(1).steps_per_switching_period, ...
            'fine_steps',pair(end).steps_per_switching_period, ...
            'output_rms_relative_percent',NaN,'thd_absolute_percentage_points',NaN, ...
            'inductor_rms_relative_percent',NaN,'inductor_peak_relative_percent',NaN, ...
            'converged',false,'comparison_group_id',pair(1).comparison_group_id, ...
            'coarse_run_id',pair(1).run_id,'fine_run_id',pair(end).run_id,'selected_run_id','', ...
            'status','incomplete','failed_criteria','missing_or_failed_run');
        valid=numel(pair)==2 && all(strcmp({pair.status},'success')) && c.coarse_steps<c.fine_steps;
        fields={'output_rms_V','thd_h2_h40_percent','inductor_rms_A','inductor_peak_A'};
        for k=1:numel(fields),valid=valid && all(isfinite([pair.(fields{k})]));end
        if valid
            c.output_rms_relative_percent=relative(pair(1).output_rms_V,pair(2).output_rms_V);
            c.thd_absolute_percentage_points=abs(pair(1).thd_h2_h40_percent-pair(2).thd_h2_h40_percent);
            c.inductor_rms_relative_percent=relative(pair(1).inductor_rms_A,pair(2).inductor_rms_A);
            c.inductor_peak_relative_percent=relative(pair(1).inductor_peak_A,pair(2).inductor_peak_A);
            values=[c.output_rms_relative_percent,c.thd_absolute_percentage_points,c.inductor_rms_relative_percent,c.inductor_peak_relative_percent];
            names={'output_rms','thd','inductor_rms','inductor_peak'};
            failed=values>=[.2,.1,.5,1];
            c.converged=~any(failed);c.status='complete';c.failed_criteria=strjoin(names(failed),',');
            c.selected_run_id=pair(2).run_id;
        end
        if isempty(comparisons),comparisons=c;else,comparisons(end+1)=c;end %#ok<AGROW>
    end
end
end
function value=relative(a,b)
value=100*abs(a-b)/max(abs(b),eps);
end
