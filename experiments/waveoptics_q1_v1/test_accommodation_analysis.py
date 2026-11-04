import unittest, tempfile,csv
from pathlib import Path
import numpy as np
from analyze_accommodation import fit_harmonic,analyze_file

class AnalysisUnitTests(unittest.TestCase):
    def test_known_phase(self):
        t=np.arange(0,30,.04);f=.1
        amplitude,phase,r2=fit_harmonic(t,2+.3*np.sin(2*np.pi*f*t-np.pi/4),f)
        self.assertAlmostEqual(amplitude,.3,places=6)
        self.assertAlmostEqual(phase,-np.pi/4,places=6)
        self.assertAlmostEqual(r2,1.,places=6)
    def test_synthetic_csv_pipeline(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'synthetic.csv';dest=Path(d)/'out.csv'
            with src.open('w',newline='') as f:
                writer=csv.writer(f)
                writer.writerow(['condition','trial_id','time_s','stimulus_D','measured_D','valid'])
                for t in np.arange(0,30,1/30):
                    stim=1.67+.45*np.sin(2*np.pi*.1*t)
                    obs=1.67+.30*np.sin(2*np.pi*.1*t-.1)
                    writer.writerow(['SYNTHETIC_ONLY','1',t,stim,obs,1])
            rows=analyze_file(src,dest,.1)
            self.assertEqual(len(rows),1)
            self.assertAlmostEqual(rows[0]['gain'],2/3,places=3)
            self.assertAlmostEqual(rows[0]['phase_lag_s'],.1/(2*np.pi*.1),places=3)
            self.assertTrue(dest.exists())

if __name__=='__main__':unittest.main()
