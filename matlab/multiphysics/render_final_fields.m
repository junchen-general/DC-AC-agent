function render_final_fields
root=fileparts(mfilename('fullpath'));
out=fullfile(root,'outputs','unit_response');
d=load(fullfile(out,'case_02.mat'));
s=d.displacement.Stress;
principal=max(0,(s.sxx+s.syy)/2+sqrt(((s.sxx-s.syy)/2).^2+s.sxy.^2));
fig=figure('Visible','off','Color','w','Position',[100,100,1550,510]);
subplot(1,3,1);pdeplot(d.thermal,'XYData',d.temperature.Temperature,'Contour','off');
axis equal tight;xlabel('x (m)');ylabel('y (m)');title('Temperature rise (K/W)');
subplot(1,3,2);pdeplot(d.structural,'XYData',d.displacement.Displacement.Magnitude*1e6,'Contour','off');
axis equal tight;xlabel('x (m)');ylabel('y (m)');title('Displacement (micrometers/W)');
subplot(1,3,3);pdeplot(d.structural,'XYData',principal*1e-6,'Contour','off');
axis equal tight;xlabel('x (m)');ylabel('y (m)');title('Maximum principal stress (MPa/W)');
sgtitle('1 W winding heat: assumed bonded assembly, h = 10 W/(m^2 K)');
colormap(parula);exportgraphics(fig,fullfile(out,'thermal_structural_fields.png'),'Resolution',170);
close(fig);
end
