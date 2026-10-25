function render_dcac_waveforms(t,y,s,metrics,outdir)
% Display switching-period extrema without undersampling instantaneous current.
dt=t(2)-t(1); ns=round(1/s.switching_frequency/dt);
nb=floor((numel(t)-1)/ns); use=1:nb*ns;
tb=mean(reshape(t(use),ns,nb),1);
f=figure('Visible','off','Color','w','Position',[100 100 1100 900]);
tiledlayout(3,1);
for j=1:2
    a=reshape(y(use,j),ns,nb);
    nexttile;
    fill([tb fliplr(tb)],[min(a,[],1) fliplr(max(a,[],1))], ...
        [.65 .78 .9],'EdgeColor','none','FaceAlpha',.65); hold on;
    plot(tb,mean(a,1),'Color',[.1 .25 .4],'LineWidth',.8); grid on;
    legend('Switch-period min/max','Switch-period mean','Location','southwest');
    xlabel('Time (s)');
    if j==1
        ylabel('Output voltage (V)');
        title(sprintf('%.2f Vrms | Output-voltage THD (2-40): %.3f%%',metrics.output_rms,metrics.thd_percent));
    else
        ylabel('Inductor current (A)');
        title('Startup and steady state; shaded band retains switching ripple');
    end
end
nexttile;
start=t(end)-1/s.output_frequency+.002;
idx=t>=start & t<=start+4/s.switching_frequency;
plot(t(idx),y(idx,2),'Color',[.1 .25 .4]); grid on;
xlabel('Time (s)'); ylabel('Inductor current (A)');
title('Steady-state detail: four switching periods, full-rate samples');
exportgraphics(f,fullfile(outdir,'waveforms.png'),'Resolution',160); close(f);
end
