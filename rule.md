CHEMICALS ICE
•	KE1_call: from DPRA + Endpoint = Call 
•	KE1_metric: median of DPRA + Endpoint = Depletion Lys + Cys 
•	KS_call: aggregated KeratinoSens call 
•	LuSens_call: aggregated LuSens call 
•	hCLAT_call: aggregated h-CLAT call 
•	USENS_call: aggregated U-SENS call 
•	KE2_call: positive if either KS_call or LuSens_call is Active 
•	KE3_call: positive if either hCLAT_call or USENS_call is Active 
•	LLNA_call: from LLNA + Endpoint = Call 
•	LLNA_EC3: median numeric LLNA + Endpoint = EC3 
•	Misclassified: 1 if any KE call differs from LLNA_call

CHEMICALS SKINSENSDB
•	KE1_metric is reconstructed as the mean of DPRA_Cys and DPRA_Lys 
•	KE1_call = 1 when KE1_metric >= 6.38 
•	KE2_metric = KeratinoSens_LuSens_EC15 
•	KE2_call = 1 when KE2_metric <= 1000 
•	KE3_metric is reconstructed as the minimum of h-CLAT_U-SENS_EC150 and h-CLAT_EC200 
•	KE3_call = 1 when EC150 <= 150 or EC200 <= 200 
•	LLNA_call = 1 when LLNA_EC3 > 0 
•	complete cases are rows where KE1_metric, KE2_metric, KE3_metric, and LLNA_EC3 are all present

Steps:
A. For ICE
ICE_Dataset.xlsx already has:
•	Data_invitro 
•	Data_invivo 
So I would reconstruct sheet 1 like this:
KE1
Use DPRA rows from Data_invitro.
•	KE1_call: from Assay = DPRA and Endpoint = Call 
•	KE1_metric: from Assay = DPRA and Endpoint = Depletion Lys + Cys (and Reported_Response = Active)
KE2
Use KeratinoSens and LuSens rows.
•	KS_call: Assay = KeratinoSens, Endpoint = Call 
•	LuSens_call: Assay = LuSens, Endpoint = Call 
•	KE2_call: positive if either assay is Active 
KE3
Use h-CLAT and U-SENS rows.
•	hCLAT_call: Assay = h-CLAT, Endpoint = Call 
•	USENS_call: Assay = U-SENS, Endpoint = Call 
•	KE3_call: positive if either assay is Active 
LLNA
Use Data_invivo.
•	LLNA_call: Assay = LLNA, Endpoint = Call 
•	LLNA_EC3: Assay = LLNA, Endpoint = EC3 
Then create presence flags:
•	KE1_metric__present 
•	KS_call__present 
•	LuSens_call__present 
•	hCLAT_call__present 
•	USENS_call__present 
•	LLNA_EC3__present

B. For SkinSensDB
KE1
From DPRA chemistry:
•	KE1_metric = mean(DPRA_Cys, DPRA_Lys) 
•	KE1_call = 1 if KE1_metric >= 6.38 else 0 
KE2
From KeratinoSens/LuSens:
•	KE2_metric = KeratinoSens_LuSens_EC15 
•	KE2_call = 1 if KE2_metric <= 1000 else 0 
KE3
From dendritic-cell assays:
•	KE3_metric = min(h-CLAT_U-SENS_EC150, h-CLAT_EC200) using whichever is available 
•	KE3_call = 1 if EC150 <= 150 or EC200 <= 200 else 0 
LLNA
•	LLNA_EC3 
•	LLNA_call = 1 if EC3 is present and positive
