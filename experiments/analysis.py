import os
import json
import configparser
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

import platform
if platform.system() == "Windows":
    BASEPATH = "d:/FogBrain\/FogArmX"
else:
    BASEPATH = "."
    
STATS_FOLDER = "/stats"

IMG_FOLDER = "/img"

cr = "2022_06_16_11"
nocr = "2022_06_20_09"

scalability = ["2022_06_15_02", "2022_06_15_09", "2022_06_16_11"]

def get(dir):
    with open(BASEPATH+STATS_FOLDER+"/"+dir+"/stats.json") as f:
        return json.load(f)

def to_df(data):
    return pd.DataFrame.from_dict(data)

def get_stats(dir):
    data = to_df(get(dir))
    print(data["Placement"])
    data["ToMigrate%"] = (data["ToMigrate"].fillna(0)/( 8 - data["ToRemove"].fillna(0) - data["ToAdd"].fillna(0)))*100
    data["Execution Times"] = data["fogbrain"].fillna(0) + data["actuate"].fillna(0)

    config = configparser.ConfigParser()
    config.read(BASEPATH+STATS_FOLDER+"/"+dir+"/config.ini")
        
    return {"data":data, "apps":int(config["EXPERIMENT"]["app_count"])*8, "nodes":int(config["INFRA"]["count"])*len(json.loads(config["INFRA"]["clouds"]))}

def gest_attr_stats(data, main_attr, sub_attrs=[]):
    sub_attrs.append(main_attr)
    data = data[data["cmd"].str.contains("exec")]
    data = data[~data["cmd"].str.contains("test")]
    try:
        data = data[data["error"].isna()]
    except KeyError:
        pass
    data = data[sub_attrs].copy()
    total_rows = data.shape[0]
    #data = data[data[main_attr].notnull()]
    data.fillna(0, inplace=True)
    res = {}
    for a in sub_attrs:
        res[a] = {}
        res[a]["mean"] = data[a].mean()
        res[a]["occ%"] = data[a].count()/total_rows*100
        res[a]["std"] = data[a].std()
        res[a]["min"] = data[a].min()
        res[a]["max"] = data[a].max()
        res[a]["median"] = data[a].median()
        res[a]["sum"] = data[a].sum()
        res[a]["all"] = data[a].tolist()

    return res


def parse_stats(dir):

    data = get_stats(dir)

    res = {}
    res["apps"] = data["apps"]
    res["nodes"] = data["nodes"]
    res["data"] = {}

    for (m, s) in [("Execution Times", []), ("ToMigrate%", [])]: 
        res["data"][m] = gest_attr_stats(data["data"], m, s)

    return res

if __name__ == "__main__":

    if not os.path.exists(BASEPATH+STATS_FOLDER+IMG_FOLDER):
        os.makedirs(BASEPATH+STATS_FOLDER+IMG_FOLDER)

    res = {"cr":parse_stats(cr), "nocr":parse_stats(nocr)}

    print("cr",res["cr"])
    print()
    print("nocr",res["nocr"])
    print()

    labels = []
    cr_data = []
    nocr_data = []

    for title,y,ls in [("time","Seconds",[("Execution Times","Execution Times","mean")]), ("operation%","Operations%",[("ToMigrate%","ToMigrate%","mean")])]:
        labels = []
        cr_data = []
        nocr_data = []
        for k,a,v in ls:
            if a == "ToMigrate":
                labels.append("Migrations")
            else:
                labels.append(a)
            cr_data.append(round(res["cr"]["data"][k][a][v],2))
            nocr_data.append(round(res["nocr"]["data"][k][a][v],2))

        x = np.arange(len(labels))  # the label locations
        width = 0.35  # the width of the bars

        fig, ax = plt.subplots()
        rects1 = ax.bar(x - width/2, cr_data, width, label='Continuous Reasoning')
        rects2 = ax.bar(x + width/2, nocr_data, width, label='Exhaustive Search')

        # Add some text for labels, title and custom x-axis tick labels, etc.
        ax.set_ylabel(y)
        plt.xticks(range(0,len(labels)), labels)
        ax.legend()

        ax.bar_label(rects1, padding=3)
        ax.bar_label(rects2, padding=3)

        fig.tight_layout()

        plt.savefig((BASEPATH+STATS_FOLDER+IMG_FOLDER+"/crvsnocr"+title+".png").replace("%",""), dpi=600)
        plt.close()
            
    values = {}
    apps = {}

    for s in scalability:
        data = get_stats(s)
        values[data["nodes"]] = parse_stats(s)["data"]
        apps[data["nodes"]] = data["apps"]

    nodes = sorted(values.keys())


    data = {}

    for k in values[nodes[0]]:
        data[k] = {}
        for a in values[nodes[0]][k]:
            data[k][a] = {}
            for v in values[nodes[0]][k][a]:
                data[k][a][v] = []
                for n in nodes:
                    data[k][a][v].append(values[n][k][a][v])

    print(nodes, apps, data)

    for k in data.keys():
        for a in data[k].keys():
            for v in data[k][a].keys():
                if v == "all":
                    continue
                labels = []
                for n in nodes:
                    labels.append(str((n, apps[n]))) #str((n, apps[n])) #n
                plt.plot(nodes, data[k][a][v], "o--", label=a)
                plt.xticks(nodes, labels)
                #plt.title(k+" "+v)
                plt.xlabel("(Nodes,Services)")
                #plt.axis('equal')

                if "%" in k:
                    plt.ylabel("Operations%")
                else:
                    if "Execution Times" in a:
                        plt.ylabel("Seconds")
                    else:
                        plt.ylabel("Avg. Operations")
                #plt.legend()
                plt.savefig((BASEPATH+STATS_FOLDER+IMG_FOLDER+"/"+k+"_"+a+"_"+v+".png").replace("%",""), dpi=600)
                plt.close()

    # for title,y,ls in [("time","Seconds",[("Execution Times","Execution Times","mean")]), ("operation%","Operations%",[("ToMigrate%","ToMigrate%","mean")])]:
    #     for scale in ["linear"]:
    #         for k,a,v in ls:
    #             plt.plot(nodes, data[k][a][v], label=a)
    #         #plt.title(title)
    #         plt.yscale(scale)
    #         plt.xlabel("Nodes")
    #         plt.ylabel(y)
    #         plt.legend()
    #         plt.savefig(BASEPATH+STATS_FOLDER+IMG_FOLDER+"/"+title+"-"+scale+".png")
    #         plt.close()
    
    fig = plt.figure()
    ax = fig.add_subplot()
    bp = ax.boxplot([res["cr"]["data"]["Execution Times"]["Execution Times"]["all"], res["nocr"]["data"]["Execution Times"]["Execution Times"]["all"]], labels=["Continuous Reasoning", "Exhaustive Search"], showmeans=True, meanline=True, medianprops=dict(linewidth=0))
    ax.set_ylabel("Seconds")
    
    for i, line in enumerate(bp['means']):
        x, y = line.get_xydata()[1]
        if i == 0:
            m1 = round(res["cr"]["data"]["Execution Times"]["Execution Times"]["mean"],2)
            st1 = round(res["cr"]["data"]["Execution Times"]["Execution Times"]["std"],2)
        else:
            m1 = round(res["nocr"]["data"]["Execution Times"]["Execution Times"]["mean"],2)
            st1 = round(res["nocr"]["data"]["Execution Times"]["Execution Times"]["std"],2)
        text = ' μ={:.2f}'.format(m1, st1)
        ax.annotate(text, xy=(x, y))
        
    plt.savefig((BASEPATH+STATS_FOLDER+IMG_FOLDER+"/crvsnocr_boxplot.png").replace("%",""), dpi=600)
    plt.close()
    
    
    fig = plt.figure()
    ax = fig.add_subplot()
    bp = ax.boxplot([res["cr"]["data"]["ToMigrate%"]["ToMigrate%"]["all"], res["nocr"]["data"]["ToMigrate%"]["ToMigrate%"]["all"]], labels=["Continuous Reasoning", "Exhaustive Search"], showmeans=True, meanline=True, medianprops=dict(linewidth=0)) #meanprops=dict(marker='o', markeredgecolor='black', markerfacecolor='firebrick')
    ax.set_ylabel("Operations%")
    
    for i, line in enumerate(bp['means']):
        x, y = line.get_xydata()[1]
        if i == 0:
            m1 = round(res["cr"]["data"]["ToMigrate%"]["ToMigrate%"]["mean"],2)
            st1 = round(res["cr"]["data"]["ToMigrate%"]["ToMigrate%"]["std"],2)
        else:
            m1 = round(res["nocr"]["data"]["ToMigrate%"]["ToMigrate%"]["mean"],2)
            st1 = round(res["nocr"]["data"]["ToMigrate%"]["ToMigrate%"]["std"],2)
        text = ' μ={:.2f}'.format(m1, st1)
        ax.annotate(text, xy=(x, y))
    plt.savefig((BASEPATH+STATS_FOLDER+IMG_FOLDER+"/crvsnocr_boxplot_migrations.png").replace("%",""), dpi=600)
    plt.close()
    
    for k in data.keys():
        for a in data[k].keys():
            fig = plt.figure()
            ax = fig.add_subplot()
            bp = ax.boxplot(data[k][a]["all"], labels=nodes, showmeans=True, meanline=True, medianprops=dict(linewidth=0))
            if "%" in k:
                ax.set_ylabel("Operations%")
            else:
                if "Execution Times" in a:
                    ax.set_ylabel("Seconds")
                else:
                    ax.set_ylabel("Avg. Operations")
            
            for i, line in enumerate(bp['means']):
                x, y = line.get_xydata()[1]
                m1 = round(np.mean(data[k][a]["all"][i]),2)
                st1 = round(np.std(data[k][a]["all"][i]),2)
                text = ' μ={:.2f}'.format(m1, st1)
                ax.annotate(text, xy=(x, y))
            
            plt.savefig((BASEPATH+STATS_FOLDER+IMG_FOLDER+"/"+k+"_"+a+"_boxplot.png").replace("%",""), dpi=600)
            plt.close()
            
    for k in data.keys():
        for a in data[k].keys():
            labels = []
            for n in nodes:
                labels.append(str((n, apps[n]))) #str((n, apps[n])) #n
            plt.plot(nodes, data[k][a]["mean"], "o--", label=a)
            avg_plus_std = [x + y for x, y in zip(data[k][a]["mean"], data[k][a]["std"])]
            avg_minus_std = [x - y for x, y in zip(data[k][a]["mean"], data[k][a]["std"])]
            
            avg_plus_std = [0 if x < 0 else x for x in avg_plus_std]
            avg_minus_std = [0 if x < 0 else x for x in avg_minus_std]
            
            if "%" in k:
                avg_plus_std = [100 if x > 100 else x for x in avg_plus_std]
                avg_minus_std = [100 if x > 100 else x for x in avg_minus_std]
            
            plt.fill_between(nodes, avg_minus_std, avg_plus_std, alpha=0.4)
            # plt.fill_between(nodes, data[k][a]["min"], data[k][a]["max"], alpha=0.2)
            plt.xticks(nodes, labels)
            #plt.title(k+" "+v)
            plt.xlabel("(Nodes,Services)")
            #plt.axis('equal')

            if "%" in k:
                plt.ylabel("Operations%")
            else:
                if "Execution Times" in a:
                    plt.ylabel("Seconds")
                else:
                    plt.ylabel("Avg. Operations")
            #plt.legend()
            plt.savefig((BASEPATH+STATS_FOLDER+IMG_FOLDER+"/"+k+"_"+a+"_with_errors.png").replace("%",""), dpi=600)
            plt.close()
    
    