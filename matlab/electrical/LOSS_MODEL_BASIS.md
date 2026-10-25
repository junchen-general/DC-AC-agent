# Loss model basis

Device: Infineon IPW65R041CFD7, 650 V CoolMOS CFD7, datasheet Rev. 2.1, 2020-08-12.

Official source: https://www.infineon.com/assets/row/public/documents/24/49/infineon-ipw65r041cfd7-datasheet-en.pdf

Parameters used by the preliminary model:

- `RDS(on)=0.076 ohm` typical at `Tj=150 C`, `VGS=10 V`, `ID=24.8 A`.
- Body-diode `VSD=1.0 V` typical at `Tj=25 C`, `IF=24.8 A`.
- `tr=12 ns`, `tf=3 ns` typical at `VDD=400 V`, `VGS=13 V`, `ID=24.8 A`, `RG=3.3 ohm`.
- `Qrr=1.2 uC` typical at `VR=400 V`, `IF=24.8 A`, `di/dt=100 A/us`.

The course-design operating current is much lower than the datasheet switching test point. The model therefore records conduction, switching-overlap and dead-time-diode estimates separately, leaves reverse-recovery as a non-included reference, and does not claim whole-inverter efficiency. The default winding resistance is also unverified and its `I^2 R` value is DC-ohmic-only.
