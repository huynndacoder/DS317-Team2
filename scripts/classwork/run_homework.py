#!/usr/bin/env python3
"""DS317 classwork: deterministic unlabeled sample, grain DQ, clustering/outliers.
Run from repo root. Does not rebuild Gold, train supervised models or evaluate 2024.
"""
import os
for key in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ.setdefault(key,"1")
import argparse, ast, csv, hashlib, importlib.util, json, math, pickle, sys, time, warnings
from pathlib import Path
import duckdb, numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.cluster import KMeans, DBSCAN
from sklearn.mixture import GaussianMixture
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.neighbors import NearestNeighbors
from sklearn.metrics import (silhouette_score,calinski_harabasz_score,davies_bouldin_score,
 adjusted_rand_score,normalized_mutual_info_score,average_precision_score,roc_auc_score,
 brier_score_loss,log_loss)
ROOT=Path(__file__).resolve().parents[2]
NUM=["original_upb","original_loan_term","original_interest_rate","ltv","cltv",
     "dti","mi_percentage","number_of_units","credit_score"]
DIM=["completeness","validity","uniqueness","consistency","accuracy","timeliness"]
G=ROOT/"output/research"
RUN=ROOT/"output/baseline/run"
PKG=ROOT/"output/baseline/report"
def clean(v):
    if isinstance(v,dict):return {str(k):clean(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [clean(x) for x in v]
    if isinstance(v,np.generic):return clean(v.item())
    if isinstance(v,float) and not math.isfinite(v):return None
    return v
def dump(p,v):p.write_text(json.dumps(clean(v),ensure_ascii=False,indent=2),encoding="utf-8")
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def accuracy_against_reference(actual,reference=None,tolerance=0):
    if reference is None:return np.full(len(actual),np.nan)
    a=np.asarray(actual,dtype=float);r=np.asarray(reference,dtype=float)
    return np.where(np.isfinite(a)&np.isfinite(r),(np.abs(a-r)<=tolerance).astype(float),np.nan)
def timeliness_from_age(age_days=None,volatility_days=30,n=1):
    if age_days is None:return np.full(n,np.nan)
    if volatility_days<=0:raise ValueError("volatility_days must be positive")
    a=np.asarray(age_days,dtype=float)
    return np.where(np.isfinite(a)&(a>=0),np.maximum(0,1-a/volatility_days),np.nan)
def psi(ref,cur):
    edges=np.unique(np.quantile(ref,np.linspace(0,1,11)))
    if len(edges)<3:
        u=np.unique(ref)
        if len(u)==1:edges=np.array([-np.inf,u[0]-1e-9,u[0]+1e-9,np.inf])
        else:edges=np.r_[-np.inf,(u[:-1]+u[1:])/2,np.inf]
    edges[0]=-np.inf;edges[-1]=np.inf
    a=np.histogram(ref,edges)[0]/len(ref);b=np.histogram(cur,edges)[0]/len(cur)
    a=np.maximum(a,1e-6);b=np.maximum(b,1e-6)
    a=a/a.sum();b=b/b.sum()
    return float(np.sum((b-a)*np.log(b/a)))
def cluster_metrics(X,labels):
    labels=np.asarray(labels);mask=labels!=-1;z=X[mask];l=labels[mask];k=len(np.unique(l))
    out={"n":len(X),"n_assigned":int(mask.sum()),"n_clusters":k,
         "noise_fraction":float((~mask).mean()),"silhouette":None,"calinski_harabasz":None,"davies_bouldin":None}
    if 1<k<len(z):
        out.update(silhouette=float(silhouette_score(z,l,sample_size=min(2000,len(z)),random_state=42)),
         calinski_harabasz=float(calinski_harabasz_score(z,l)),
         davies_bouldin=float(davies_bouldin_score(z,l)))
    return out
def main():
    pa=argparse.ArgumentParser();pa.add_argument("--out-dir",required=True)
    pa.add_argument("--reference-n",type=int,default=8000);pa.add_argument("--monitor-n",type=int,default=4000)
    args=pa.parse_args();out=Path(args.out_dir)
    if out.exists() and any(out.iterdir()):raise SystemExit("Output must be new/empty")
    out.mkdir(parents=True,exist_ok=True);(out/"figures").mkdir()
    before={str(p.relative_to(ROOT)):sha(p) for p in RUN.rglob("*") if p.is_file()}
    t0=time.time();con=duckdb.connect();con.execute("SET memory_limit='2GB'");con.execute("SET threads=2")
    print("1/6 Inventory and deterministic sample (no target read for selection)",flush=True)
    spec=importlib.util.spec_from_file_location("course_gold_spec",ROOT/"scripts/gold/gold_spec.py")
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);features=mod.BASELINE
    tree=ast.parse((ROOT/"scripts/gold/build_research_dataset.py").read_text())
    valid=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="VALID" for t in n.targets)))
    inventory=[]
    for name,pat in [("origination","parquet/orig/quarter=*/data.parquet"),
                     ("performance","parquet/perf/quarter=*/data.parquet"),
                     ("labels","output/labels/cohort=*/data.parquet"),
                     ("research_features","output/research/features.parquet")]:
        fs=sorted(ROOT.glob(pat))
        if not fs:
            inventory.append({"table":name,"rows":None,"files":0,"bytes":0,"note":"Not present locally: metadata-only inventory skipped; no rows inferred."})
            continue
        n=con.execute("SELECT sum(num_rows) FROM parquet_file_metadata(?)",[str(ROOT/pat)]).fetchone()[0]
        inventory.append({"table":name,"rows":n,"files":len(fs),"bytes":sum(p.stat().st_size for p in fs)})
    con.read_parquet(str(G/"features.parquet")).create_view("f")
    con.read_parquet(str(G/"split.parquet")).create_view("s")
    con.read_parquet(str(G/"membership.parquet")).create_view("m")
    a=con.execute("SELECT f.*,s.cohort,s.first_payment_date,s.label_window_end FROM f JOIN s USING(loan_id) JOIN m USING(loan_id) WHERE m.role='train_refit' ORDER BY md5(f.loan_id) LIMIT ?",[args.reference_n]).df()
    b=con.execute("SELECT f.*,s.cohort,s.first_payment_date,s.label_window_end FROM f JOIN s USING(loan_id) JOIN m USING(loan_id) WHERE m.role='development_test' ORDER BY md5(f.loan_id) LIMIT ?",[args.monitor_n]).df()
    a["phase"]="reference_2012_2016";b["phase"]="monitor_2019"
    sample=pd.concat([a,b],ignore_index=True);assert sample.loan_id.is_unique
    assert not sample.cohort.str.startswith("2024").any()
    assert set(a.loan_id).isdisjoint(set(b.loan_id))
    con.register("sample_ids",sample[["loan_id","cohort","phase"]])
    raw=con.execute("SELECT o.*,i.cohort,i.phase FROM read_parquet('parquet/orig/quarter=*/data.parquet',hive_partitioning=true) o JOIN sample_ids i USING(loan_id)").df()
    raw=raw.set_index("loan_id").loc[sample.loan_id].reset_index()
    assert len(raw)==len(sample)
    sample[["loan_id","cohort","phase"]].to_parquet(out/"sample_membership.parquet",index=False)
    dict_rows=[d for d in mod.D if d["column"] in features]
    pd.DataFrame(dict_rows).to_csv(out/"feature_dictionary.csv",index=False)
    pd.read_csv(ROOT/"output/schema/orig_schema.csv").to_csv(out/"orig_schema.csv",index=False)
    print("2/6 Six dimensions at loan grain; missing evidence remains N/A",flush=True)
    misscodes={"credit_score":9999,"dti":999,"ltv":999,"cltv":999,"mi_percentage":999,
       "number_of_units":99,"number_of_borrowers":99,"first_time_homebuyer_flag":"9",
       "channel":"9","property_type":"99","occupancy_status":"9",
       "prepayment_penalty_flag":"9","super_conforming_flag":"9","harp_indicator":"9"}
    grains=[];detail=[]
    for version,frame in [("raw",raw),("normalized",sample)]:
        frame=frame.copy();present=[];good=[];applicable=[]
        con.register("dq_frame",frame.assign(quarter=frame.cohort))
        for f in features:
            x=frame[f];p=x.notna()&(x.astype(str).str.strip()!="")
            if version=="raw" and f in misscodes:p=p&(x!=misscodes[f])
            if version=="raw":
                ok=con.execute("SELECT coalesce(("+valid[f]+"),false) FROM dq_frame").df().iloc[:,0].to_numpy()
            elif f=="number_of_borrowers":ok=x.isin(["one","multiple"]).to_numpy()
            else:ok=con.execute("SELECT coalesce(("+valid[f]+"),false) FROM dq_frame").df().iloc[:,0].to_numpy()
            present.append(p.to_numpy());good.append(ok&p.to_numpy());applicable.append(p.to_numpy())
            for cohort,ix in frame.groupby("cohort").groups.items():
                ar=np.asarray(list(ix));den=int(p.iloc[ar].sum())
                detail.append({"version":version,"cohort":cohort,"feature":f,"n":len(ar),
                 "present":den,"valid":int((ok[ar]&p.iloc[ar].to_numpy()).sum()),"validity_denominator":den})
        P=np.stack(present,1);V=np.stack(good,1);den=P.sum(1)
        # Applicable-only cross-field consistency. Neither rule establishes real-world accuracy.
        rr=raw
        ltv=pd.to_numeric(frame.ltv,errors="coerce");cltv=pd.to_numeric(frame.cltv,errors="coerce")
        cross_app=ltv.notna()&cltv.notna()&(ltv!=999)&(cltv!=999)
        date_app=rr.first_payment_date.notna()&rr.maturity_date.notna()
        good_cross=(cltv>=ltv)&cross_app
        good_dates=(rr.first_payment_date<=rr.maturity_date)&date_app
        cden=cross_app.astype(int)+date_app.astype(int)
        scores=pd.DataFrame({"loan_id":sample.loan_id,"cohort":sample.cohort,"phase":sample.phase,"version":version,
          "completeness":P.mean(1),"validity":np.divide(V.sum(1),den,out=np.full(len(den),np.nan),where=den>0),
          "uniqueness":(~frame.loan_id.duplicated(keep=False)).astype(float),
          "consistency":(good_cross.astype(int)+good_dates.astype(int))/cden.replace(0,np.nan),
          "accuracy":accuracy_against_reference(np.zeros(len(frame))),
          "timeliness":timeliness_from_age(n=len(frame)),
          "validity_applicable_cells":den,"consistency_applicable_rules":cden,
          "physical_completeness":frame[features].notna().mean(axis=1)})
        end=sample.label_window_end.astype(int);ready=(end//100*12+end%100+3<=2019*12+1)
        scores["label_ready_at_201901_proxy"]=ready.astype(float)
        grains.append(scores)
    grain=pd.concat(grains,ignore_index=True);grain.to_parquet(out/"dq_grain.parquet",index=False)
    long=grain.melt(id_vars=["loan_id","cohort","phase","version"],value_vars=DIM,var_name="dimension",value_name="score")
    agg=long.groupby(["version","phase","cohort","dimension"],dropna=False).score.agg(["mean","count","size"]).reset_index()
    agg.rename(columns={"mean":"score","count":"n_measurable","size":"n_rows"},inplace=True)
    agg.to_csv(out/"dq_by_cohort.csv",index=False)
    overall=long.groupby(["version","dimension"]).score.agg(["mean","count","size"]).reset_index()
    overall.rename(columns={"mean":"score","count":"n_measurable","size":"n_rows"},inplace=True)
    overall.to_csv(out/"dq_overall.csv",index=False);pd.DataFrame(detail).to_csv(out/"dq_by_feature_cohort.csv",index=False)
    fig,axs=plt.subplots(3,2,figsize=(13,10))
    for dim,ax in zip(DIM,axs.flat):
        part=agg[agg.dimension==dim]
        for ver,g in part.groupby("version"):
            g=g.sort_values("cohort");ax.plot(g.cohort,g.score,marker=".",label=ver)
        ax.set_title(dim);ax.tick_params(axis="x",rotation=90,labelsize=7);ax.set_ylim(-.02,1.02)
        if part.n_measurable.sum()==0:ax.text(.5,.5,"N/A: no independent reference / publication timestamps",ha="center",wrap=True,transform=ax.transAxes)
        ax.grid(alpha=.2)
    axs[0,0].legend();fig.suptitle("DQ: deterministic 12,000-loan classwork sample; not whole portfolio")
    fig.tight_layout();fig.savefig(out/"figures/dq_by_cohort.png",dpi=150);plt.close(fig)
    print("3/6 Unsupervised fitting without labels",flush=True)
    xa=a[NUM].astype(float).copy();xb=b[NUM].astype(float).copy()
    xa["original_upb"]=np.log1p(xa.original_upb);xb["original_upb"]=np.log1p(xb.original_upb)
    imp=SimpleImputer(strategy="median",add_indicator=True);scaler=StandardScaler()
    X=scaler.fit_transform(imp.fit_transform(xa));Z=scaler.transform(imp.transform(xb))
    trials=[];best=None
    for k in range(2,7):
        t=time.time();km=KMeans(n_clusters=k,n_init=10,random_state=42);lab=km.fit_predict(X)
        met=cluster_metrics(X,lab);met.update(model="KMeans",k=k,inertia=km.inertia_,fit_seconds=time.time()-t)
        trials.append(met)
        if best is None or met["silhouette"]>best[0]:best=(met["silhouette"],km,lab,met)
    _,km,kl,kmet=best
    gmm=GaussianMixture(n_components=km.n_clusters,covariance_type="full",reg_covar=1e-5,n_init=2,random_state=42,max_iter=200)
    t=time.time();gl=gmm.fit_predict(X);gmet=cluster_metrics(X,gl);gmet.update(model="GMM",fit_seconds=time.time()-t,bic=gmm.bic(X),converged=bool(gmm.converged_))
    nn=NearestNeighbors(n_neighbors=20,n_jobs=2).fit(X)
    dist=nn.kneighbors(X)[0][:,-1];eps=max(float(np.quantile(dist,.90)),1e-6)
    t=time.time();db=DBSCAN(eps=eps,min_samples=20,n_jobs=2).fit(X);dl=db.labels_
    dmet=cluster_metrics(X,dl);dmet.update(model="DBSCAN",fit_seconds=time.time()-t,eps=eps,min_samples=20)
    km2=KMeans(n_clusters=km.n_clusters,n_init=10,random_state=43).fit(X)
    kmet["stability_ari_seed42_43"]=float(adjusted_rand_score(kl,km2.labels_))
    iso=IsolationForest(n_estimators=100,max_samples=256,contamination=.01,random_state=42,n_jobs=2).fit(X)
    q1=np.nanquantile(xa,.25,axis=0);q3=np.nanquantile(xa,.75,axis=0);iqr=q3-q1
    def iqr_score(x):
        v=np.asarray(x);spread=np.where(iqr>0,iqr,np.nan)
        excess=np.maximum((q1-1.5*iqr-v)/spread,(v-q3-1.5*iqr)/spread)
        return np.nanmax(np.nan_to_num(excess,nan=0),axis=1).clip(min=0)
    ir=iqr_score(xa);im=iqr_score(xb)
    scored=pd.DataFrame({"loan_id":sample.loan_id,"phase":sample.phase,"cohort":sample.cohort,
      "kmeans_cluster":np.r_[kl,km.predict(Z)],"gmm_cluster":np.r_[gl,gmm.predict(Z)],
      "dbscan_reference_cluster":np.r_[dl,np.full(len(b),-999)],
      "isolation_score":-iso.score_samples(np.vstack([X,Z])),
      "isolation_flag":iso.predict(np.vstack([X,Z]))==-1,"iqr_score":np.r_[ir,im],"iqr_flag":np.r_[ir>0,im>0]})
    # Outcomes are joined only after hyperparameters, fitting and scoring are finished.
    print("4/6 Post-hoc external diagnostics (delinquency is NOT anomaly ground truth)",flush=True)
    y=con.execute("SELECT t.loan_id,t.label_12m FROM read_parquet(?) t JOIN sample_ids i USING(loan_id)",[str(G/"target.parquet")]).df()
    scored=scored.merge(y,on="loan_id",validate="one_to_one",sort=False)
    assert len(scored)==len(sample)
    scored.to_parquet(out/"unsupervised_scores.parquet",index=False)
    ref=scored[scored.phase=="reference_2012_2016"]
    for lab,met in [(kl,kmet),(gl,gmet),(dl,dmet)]:
        mask=lab!=-1;l=np.asarray(lab)[mask];yy=ref.label_12m.to_numpy()[mask]
        ct=pd.crosstab(l,yy)
        met.update(reference_outcome_purity=float(ct.max(axis=1).sum()/ct.to_numpy().sum()),
          reference_outcome_entropy=float(sum((r.sum()/ct.to_numpy().sum())*(-sum((v/r.sum())*math.log2(v/r.sum()) for v in r if v>0)) for r in ct.to_numpy())),
          reference_outcome_ari=float(adjusted_rand_score(yy,l)),reference_outcome_nmi=float(normalized_mutual_info_score(yy,l)))
    pd.DataFrame([kmet,gmet,dmet]).to_csv(out/"clustering_metrics.csv",index=False)
    pd.DataFrame(trials).to_csv(out/"kmeans_k_selection.csv",index=False)
    profiles=a[NUM].assign(cluster=kl).groupby("cluster").median()
    profiles["n"]=pd.Series(kl).value_counts().sort_index()
    profiles.to_csv(out/"cluster_profiles.csv")
    outcomes=ref.groupby("kmeans_cluster").label_12m.agg(["size","sum","mean"]).reset_index()
    outcomes.to_csv(out/"cluster_outcomes_posthoc.csv",index=False)
    alerts=scored.groupby("phase")[["isolation_flag","iqr_flag"]].mean().reset_index()
    alerts.to_csv(out/"outlier_alert_rates.csv",index=False)
    proxies=[]
    for phase,g in scored.groupby("phase"):
        for col in ["isolation_score","iqr_score"]:
            proxies.append({"phase":phase,"method":col,"n":len(g),"positives":int(g.label_12m.sum()),
              "AP_against_delinquency_proxy":float(average_precision_score(g.label_12m,g[col]))})
    pd.DataFrame(proxies).to_csv(out/"outlier_external_proxy.csv",index=False)
    drift=[{"feature":f,"psi":psi(X[:,i],Z[:,i])} for i,f in enumerate(NUM)]
    pd.DataFrame(drift).to_csv(out/"drift_psi.csv",index=False)
    pca=PCA(n_components=2,random_state=42).fit(X);xy=pca.transform(X)
    fig,axs=plt.subplots(1,3,figsize=(15,4))
    for ax,l,title in zip(axs,[kl,gl,dl],["KMeans","GMM","DBSCAN (-1=noise)"]):
        ax.scatter(xy[:,0],xy[:,1],c=l,s=3,cmap="tab10",alpha=.5);ax.set_title(title)
        ax.set_xlabel("PC1");ax.set_ylabel("PC2")
    fig.suptitle("PCA for visualization only; models fitted in standardized feature space")
    fig.tight_layout();fig.savefig(out/"figures/clustering_pca.png",dpi=150);plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(12,4))
    trials_df=pd.DataFrame(trials);axs[0].plot(trials_df.k,trials_df.silhouette,marker="o");axs[0].set(xlabel="k",ylabel="Silhouette (sample<=2000)")
    dp=pd.DataFrame(drift);axs[1].barh(dp.feature,dp.psi);axs[1].axvline(.25,color="r",ls="--");axs[1].set_xlabel("PSI: reference vs 2019, training bins")
    fig.tight_layout();fig.savefig(out/"figures/selection_and_drift.png",dpi=150);plt.close(fig)
    with (out/"unsupervised_bundle.pkl").open("wb") as h:pickle.dump({"numeric_features":NUM,"log1p":["original_upb"],"imputer":imp,"scaler":scaler,"kmeans":km,"gmm":gmm,"dbscan":db,"isolation_forest":iso,"pca":pca},h)
    print("5/6 Existing supervised pilot and late-label monitoring",flush=True)
    pooled=pd.read_csv(PKG/"metrics/pooled.csv")
    baseline=[];quarter=[]
    for model,tag in [("logistic_regression","lr"),("xgboost","xgb")]:
        pred=pd.read_parquet(RUN/f"predictions/development_test_{tag}.parquet")
        yy=pred.label_12m.to_numpy();pp=pred.score.to_numpy()
        assert pred.loan_id.is_unique and np.isfinite(pp).all() and ((pp>=0)&(pp<=1)).all()
        r=pooled[(pooled.model==model)&(pooled.stage=="stage_B_development_test")].iloc[0]
        met={"model":model,"n":len(pred),"n_pos":int(yy.sum()),"AP":float(average_precision_score(yy,pp)),
           "ROC_AUC":float(roc_auc_score(yy,pp)),"Brier":float(brier_score_loss(yy,pp)),"LogLoss":float(log_loss(yy,pp))}
        for akey,bkey in [("AP","average_precision_global"),("ROC_AUC","roc_auc_global"),("Brier","brier_global"),("LogLoss","log_loss_global")]:
            assert abs(met[akey]-r[bkey])<1e-8
        tp=sel=0
        for cohort,g in pred.groupby("cohort"):
            k=math.ceil(.05*len(g));top=g.sort_values(["score","loan_id"],ascending=[False,True]).head(k)
            qtp=int(top.label_12m.sum());tp+=qtp;sel+=k
            quarter.append({"model":model,"cohort":cohort,"n":len(g),"n_pos":int(g.label_12m.sum()),
              "AP":average_precision_score(g.label_12m,g.score),"capture":qtp/g.label_12m.sum(),
              "tp":qtp,"selected":k,"mean_score":float(g.score.mean()),"nan_scores":int(g.score.isna().sum())})
        assert tp==r.total_tp and sel==r.total_selected
        fp=sel-tp;fn=int(yy.sum())-tp;tn=len(yy)-tp-fp-fn
        met.update(selected=sel,TP=tp,FP=fp,FN=fn,TN=tn,capture=tp/int(yy.sum()),
          precision=tp/sel,lift=(tp/sel)/(yy.mean()),accuracy=(tp+tn)/len(yy),
          specificity=tn/(tn+fp),fpr=fp/(tn+fp),f1=2*tp/(2*tp+fp+fn))
        baseline.append(met)
    pd.DataFrame(baseline).to_csv(out/"pilot_recomputed.csv",index=False)
    pd.DataFrame(quarter).to_csv(out/"monitoring_2019.csv",index=False)
    fig,axs=plt.subplots(1,2,figsize=(12,4))
    for name,g in pd.DataFrame(quarter).groupby("model"):
        axs[0].plot(g.cohort,g.AP,marker="o",label=name)
        axs[1].plot(g.cohort,g.capture,marker="o",label=name)
    axs[0].set_title("AP by cohort: descriptive retrospective monitoring")
    axs[1].set_title("Quarterly-budget capture");axs[0].legend();axs[1].legend()
    fig.tight_layout();fig.savefig(out/"figures/model_monitoring.png",dpi=150);plt.close(fig)
    assert np.allclose(accuracy_against_reference([1,2],[1,3]),[1,0])
    assert np.isnan(accuracy_against_reference([1])[0])
    assert np.allclose(timeliness_from_age([0,15,30],30),[1,.5,0])
    assert psi(np.arange(100),np.arange(100))==0
    assert psi(np.ones(10),np.ones(10)*2)>0
    after={str(p.relative_to(ROOT)):sha(p) for p in RUN.rglob("*") if p.is_file()}
    assert before==after
    role_counts=con.execute("SELECT role,count(*) n FROM m GROUP BY role ORDER BY role").df()
    role_counts.to_csv(out/"pilot_membership_counts.csv",index=False)
    result={"generated_at_utc":pd.Timestamp.now(tz="UTC").isoformat(),"inventory":inventory,
       "sample":{"reference_n":len(a),"monitor_n":len(b),"seed":42,"selection":"ORDER BY md5(loan_id), independent of label",
        "reference_role":"train_refit","monitor_role":"development_test","holdout_2024_read_for_model_metrics":False},
       "dq_scope":"Only the deterministic classwork sample; not a full-portfolio DQ result",
       "dq_overall":overall.to_dict("records"),"clustering":[kmet,gmet,dmet],
       "outlier_rates":alerts.to_dict("records"),"drift_psi":drift,"pilot":baseline,
       "no_supervised_retraining":True,"frozen_run_hashes_unchanged":len(before),
       "sanity_checks":["reference_accuracy_known_answer","missing_reference_NA","timeliness_known_answer","zero_PSI_same_distribution","frozen_run_SHA256"],
       "runtime_seconds":time.time()-t0,"source_sha256":sha(Path(__file__)),
       "limitations":["Accuracy has no independent trusted reference; actual score N/A.",
          "No field publication timestamps; actual timeliness N/A. Readiness proxy is separate.",
          "Default outcome is not ground truth for clusters/anomalies.",
          "DBSCAN metrics exclude noise and report coverage; no out-of-sample predict used.",
          "Only numeric features used for clustering; categorical information is omitted.",
          "RF is proposed but not trained; teacher minimum three methods remains a project requirement."]}
    dump(out/"evidence.json",result)
    dump(out/"frozen_run_sha256.json",before)
    print("6/6 Complete:",str(out), "seconds",round(time.time()-t0,1),flush=True)
    print(json.dumps(clean(result),ensure_ascii=False))
if __name__=="__main__":main()
