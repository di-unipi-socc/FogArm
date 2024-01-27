import os
import time
import shutil

from utils import *

from fogArmX import store_app

MAIN_FOLDER = "."
BASE_FOLDER = MAIN_FOLDER+"/test"

TOT = 0
PASSED = 0
FAILED = []

def mkdir(path):
    if not os.path.exists(path):
        os.makedirs(path)

def mkfile(path, content):
    with open(path, "w+") as f:
        f.write(content)

def test_scenario(scenario):
    global TOT
    global PASSED
    TOT += 1
    shutil.copyfile(BASE_FOLDER+f"/scenarios/{scenario}/docker-compose.yml", BASE_FOLDER+"/docker-compose.yml")
    shutil.copyfile(BASE_FOLDER+f"/scenarios/{scenario}/requirements.yml", BASE_FOLDER+"/requirements.yml")
    shutil.copyfile(BASE_FOLDER+f"/scenarios/{scenario}/infra.pl", MAIN_FOLDER+"/infrastructure/infra.pl")

    if execute_cmd("fogarmx add "+BASE_FOLDER):
        if verify_placement("test"):
            print("-------------------------------------------------------------")
            print(f"*** Scenario '{scenario}': PASSED ***")
            print("-------------------------------------------------------------")
            PASSED += 1
            return True
        else:
            print("-------------------------------------------------------------")
            print(f"*** Scenario '{scenario}': FAILED ***")
            FAILED.append(scenario)
            print("-------------------------------------------------------------")
    else:
        print("-------------------------------------------------------------")
        print(f"* Scenario '{scenario}': AN ERROR OCCURED")
        FAILED.append(scenario)
        print("-------------------------------------------------------------")
    return False


if __name__ == "__main__":

    mkdir(MAIN_FOLDER+"/infrastructure")
    mkfile(MAIN_FOLDER+"/infrastructure/infra.pl", "")

    print("Building applications...")
    execute_cmd("docker-compose build", cwd=BASE_FOLDER)
    print("Pushing application...")
    execute_cmd("docker-compose push", cwd=BASE_FOLDER)
    print("Application ready")

    print("-------------------------------------------------------------")
    print("*** TESTING SCENARIOS ***")
    print("\nPlease, be sure that a registry is running and\nthe test service is pushed to it") 
    print("-------------------------------------------------------------")
    
    execute_cmd("fogarmx watcher stop")
    execute_cmd("fogarmx rm test")
    time.sleep(10)
    store_app(BASE_FOLDER)
    scenarios = sorted(os.listdir(BASE_FOLDER+"/scenarios"))
    for scenario in scenarios:
        print("-------------------------------------------------------------")
        print(f"*** Starting Scenario '{scenario}' ***")
        print("-------------------------------------------------------------")
        test_scenario(scenario)

    execute_cmd("fogarmx rm test")

    print("-------------------------------------------------------------")
    if TOT != 0:
        if PASSED == TOT:
            print(f"RESULTS: {(PASSED/TOT)*100}% ({PASSED}/{TOT}) SUCCESS!")
        else:
            print(f"RESULTS: {(PASSED/TOT)*100}% ({PASSED}/{TOT}) SUCCESS")
            print(f"FAILED SCENARIOS: {FAILED}")
    else:
        print("0 SCENARIOS TESTED")
    print("-------------------------------------------------------------")

    
