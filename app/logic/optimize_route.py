import sys, os
# ensure workspace root is on path for direct execution
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import gurobipy as gp
from app.services.tfl_requests import TflRequest

class OptimizeRoute:
    def __init__(self):
        self.tfl = TflRequest()
        self.all_stations = self.tfl.get_all_stations()

    def optimize(self, start_stations):
        # start_stations: list of naptan codes
        # Compute time matrix: time[s][d] = journey time from s to d
        time_matrix = {}
        path_matrix = {}
        for s in start_stations:
            time_matrix[s] = {}
            path_matrix[s] = {}
            for d in self.all_stations:
                if s == d:
                    time_matrix[s][d] = 0
                    path_matrix[s][d] = [s]
                else:
                    try:
                        time, path = self.tfl.get_journey_time_with_penalty(s, d)
                        time_matrix[s][d] = time
                        path_matrix[s][d] = path
                    except KeyError:
                        # No path, set to infinity
                        time_matrix[s][d] = float('inf')
                        path_matrix[s][d] = None

        # Use Gurobi for optimization

        # First, minimize total time
        model1 = gp.Model("min_total_time")
        model1.setParam('OutputFlag', 0)  # Silent
        d_vars1 = model1.addVars(self.all_stations, vtype=gp.GRB.BINARY, name="d")
        model1.addConstr(gp.quicksum(d_vars1[d] for d in self.all_stations) == 1)
        obj1 = gp.quicksum(time_matrix[s][d] * d_vars1[d] for s in start_stations for d in self.all_stations if time_matrix[s][d] < float('inf'))
        model1.setObjective(obj1, gp.GRB.MINIMIZE)
        model1.optimize()
        best_d_total = [d for d in self.all_stations if d_vars1[d].X > 0.5][0]

        # Second, minimize variance
        model2 = gp.Model("min_variance")
        model2.setParam('OutputFlag', 0)
        d_vars2 = model2.addVars(self.all_stations, vtype=gp.GRB.BINARY, name="d")
        model2.addConstr(gp.quicksum(d_vars2[d] for d in self.all_stations) == 1)
        t_vars = model2.addVars(start_stations, name="t")
        for s in start_stations:
            model2.addConstr(t_vars[s] == gp.quicksum(time_matrix[s][d] * d_vars2[d] for d in self.all_stations if time_matrix[s][d] < float('inf')))
        sum_t = gp.quicksum(t_vars[s] for s in start_stations)
        sum_t2 = gp.quicksum(t_vars[s] * t_vars[s] for s in start_stations)
        n = len(start_stations)
        obj2 = (1/n) * sum_t2 - (1/(n**2)) * sum_t * sum_t
        model2.setObjective(obj2, gp.GRB.MINIMIZE)
        model2.optimize()
        best_d_var = [d for d in self.all_stations if d_vars2[d].X > 0.5][0]

        # Get the routes
        routes_total = {s: path_matrix[s][best_d_total] for s in start_stations}
        routes_var = {s: path_matrix[s][best_d_var] for s in start_stations}

        return {
            'total_time_destination': best_d_total,
            'total_time_routes': routes_total,
            'variance_destination': best_d_var,
            'variance_routes': routes_var
        }


if __name__ == "__main__":
    # simple smoke tests with a few known stations
    optimizer = OptimizeRoute()

    # example group: Harrow & Wealdstone (940GZZLUHAW), Kenton (940GZZLUKEN)
    starts = ["940GZZLUHAW", "940GZZLUKEN"] # Harrow & Wealdstone and Kenton
    result = optimizer.optimize(starts)
    print("Test group 1 (adjacent stations):")
    print(result)

    # another example: two LHR terminals without a direct train
    starts = ["940GZZLUHR5", "940GZZLUHR4"]  # Heathrow T5 and T4
    result = optimizer.optimize(starts)
    print("\nTest group 2 (same line):")
    print(result)

    # larger group, random sample (could fail if station unreachable)
    starts = ["940GZZLUWYP", "940GZZLUSTM", "940GZZLUCHX"] # Wembley Park, Stanmore, Charing Cross
    result = optimizer.optimize(starts)
    print("\nTest group 3 (three stations):")
    print(result)

    # edge case: single station - destination should be itself
    starts = ["940GZZLUHAW"] # Harrow & Wealdstone
    result = optimizer.optimize(starts)
    print("\nTest group 4 (single station):")
    print(result)

