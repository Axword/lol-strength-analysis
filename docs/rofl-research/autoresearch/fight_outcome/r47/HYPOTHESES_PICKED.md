# R47 hypotheses (auto-picked)

1. **H0** Baseline remesaure vs STATUS S0 0.9304 / S1 0.7628 / c2 mae 111.6  
2. **H1** Post-lethal ally residual follow → pathMae≤90  
3. **H2** Post-lethal max-early / min-allies knobs  
4. **H3** Ally residual damaging pulses at skill_used times  
5. **H4** Ally-gated engage→kill path follow (not global)  
6. **H5** Global pathFollow control (R33/R40 regress check on new stack)  
7. **H6** allyResidualMinAllies sweep 2–5  
8. **H7** Product default KEEP + `--no-ally-gated` ablation  

KEEP = H4/H7. Discard H1–H3. H5 research-only (global flag stays false).
