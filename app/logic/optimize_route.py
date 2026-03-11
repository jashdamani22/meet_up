import sys, os
# ensure workspace root is on path for direct execution
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import gurobipy as gp
from app.services.tfl_requests import TflRequest
from app.services.restaurant_finder import RestaurantFinder

class OptimizeRoute:
    def __init__(self):
        self.tfl = TflRequest()
        self.restaurant_finder = RestaurantFinder(self.tfl)
        self.all_stations = self.tfl.get_all_stations()
        
        # Get current closed stations
        closures_info = self.tfl.get_tube_closures()
        # Extract closed station IDs (exclude 'timestamp' key)
        self.closed_stations = set(
            station_id for station_id in closures_info.keys()
            if station_id != 'timestamp'
        )

    def optimize(self, start_stations, objective='total_time', poi_constraint=None):
        """
        Optimize meeting station selection with optional POI constraints.
        
        Args:
            start_stations: List of naptan codes for starting locations
            objective: 'total_time' or 'variance' (default: 'total_time')
            poi_constraint: Optional dict with POI requirements:
                - 'type': Type of POI ('restaurant', 'pub', 'park', 'cafe', etc.)
                - 'min_count': Minimum number of POIs required (default: 5)
                - 'min_rating': Minimum rating filter (default: 3.0)
                - 'max_distance': Maximum walking distance in meters (default: 500)
                
        Returns:
            Dict with results including destination station and routes
            
        Example:
            poi_constraint = {
                'type': 'restaurant',
                'min_count': 10,
                'min_rating': 4.0,
                'max_distance': 500
            }
            result = optimizer.optimize(start_stations, poi_constraint=poi_constraint)
        """
        # Compute time and path matrices
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
                        time_matrix[s][d] = float('inf')
                        path_matrix[s][d] = None
        
        # If POI constraint is specified, use iterative approach
        if poi_constraint:
            return self._optimize_with_poi_constraint(
                start_stations, time_matrix, path_matrix, objective, poi_constraint
            )
        else:
            return self._optimize_basic(
                start_stations, time_matrix, path_matrix, objective
            )

    def _optimize_basic(self, start_stations, time_matrix, path_matrix, objective):
        """
        Basic optimization without POI constraints.
        Finds the station that minimizes either total travel time or variance.
        """
        if objective == 'total_time':
            return self._optimize_total_time(start_stations, time_matrix, path_matrix, objective)
        elif objective == 'variance':
            return self._optimize_variance(start_stations, time_matrix, path_matrix, objective)
        else:
            raise ValueError(f"Unknown objective: {objective}")

    def _optimize_total_time(self, start_stations, time_matrix, path_matrix, objective):
        """Minimize total combined travel time for all participants."""
        model = gp.Model("min_total_time")
        model.setParam('OutputFlag', 0)
        d_vars = model.addVars(self.all_stations, vtype=gp.GRB.BINARY, name="d")
        model.addConstr(gp.quicksum(d_vars[d] for d in self.all_stations) == 1)
        obj = gp.quicksum(
            time_matrix[s][d] * d_vars[d]
            for s in start_stations
            for d in self.all_stations
            if time_matrix[s][d] < float('inf')
        )
        model.setObjective(obj, gp.GRB.MINIMIZE)
        model.optimize()
        best_d = [d for d in self.all_stations if d_vars[d].X > 0.5][0]
        
        routes = {s: path_matrix[s][best_d] for s in start_stations}
        return {
            'destination': best_d,
            'routes': routes,
            'objective': objective,
            'poi_constraint_met': None
        }

    def _optimize_variance(self, start_stations, time_matrix, path_matrix, objective):
        """Minimize variance in travel times across participants."""
        model = gp.Model("min_variance")
        model.setParam('OutputFlag', 0)
        d_vars = model.addVars(self.all_stations, vtype=gp.GRB.BINARY, name="d")
        model.addConstr(gp.quicksum(d_vars[d] for d in self.all_stations) == 1)
        t_vars = model.addVars(start_stations, name="t")
        for s in start_stations:
            model.addConstr(
                t_vars[s] == gp.quicksum(
                    time_matrix[s][d] * d_vars[d]
                    for d in self.all_stations
                    if time_matrix[s][d] < float('inf')
                )
            )
        sum_t = gp.quicksum(t_vars[s] for s in start_stations)
        sum_t2 = gp.quicksum(t_vars[s] * t_vars[s] for s in start_stations)
        n = len(start_stations)
        obj = (1/n) * sum_t2 - (1/(n**2)) * sum_t * sum_t
        model.setObjective(obj, gp.GRB.MINIMIZE)
        model.optimize()
        best_d = [d for d in self.all_stations if d_vars[d].X > 0.5][0]
        
        routes = {s: path_matrix[s][best_d] for s in start_stations}
        return {
            'destination': best_d,
            'routes': routes,
            'objective': objective,
            'poi_constraint_met': None
        }

    def _optimize_with_poi_constraint(self, start_stations, time_matrix, path_matrix, objective, poi_constraint):
        """
        Optimization with POI constraint using iterative refinement.
        
        Strategy: 
        1. Solve for optimal station
        2. Check if it meets POI requirements
        3. If not, add constraint to exclude it and re-solve
        4. Repeat until a feasible solution is found or all stations exhausted
        
        This approach minimizes Google Maps API calls since we only check stations
        that are actually optimal solutions, rather than pre-fetching all POI data.
        """
        # Validate POI constraint
        if 'type' not in poi_constraint:
            raise ValueError("POI constraint must include 'type' field")
        
        poi_type = poi_constraint['type']
        min_count = poi_constraint.get('min_count', 5)
        min_rating = poi_constraint.get('min_rating', 3.0)
        max_distance = poi_constraint.get('max_distance', 750)
        
        print(f"Searching for station with at least {min_count} {poi_type}(s) rated >= {min_rating}")
        
        iteration = 0
        max_iterations = len(self.all_stations)
        excluded_stations = set()
        
        while iteration < max_iterations:
            iteration += 1
            
            # Build and solve optimization model, excluding previously infeasible stations
            model = self._build_optimization_model(
                start_stations, time_matrix, objective, excluded_stations
            )
            model.optimize()
            
            if model.status != gp.GRB.OPTIMAL:
                raise ValueError(f"Optimization failed with status {model.status}")
            
            # Extract the chosen destination station
            d_vars = {v.VarName: v for v in model.getVars() if v.VarName.startswith('d[')}
            best_d = None
            for station in self.all_stations:
                var_name = f'd[{station}]'
                if var_name in d_vars and d_vars[var_name].X > 0.5:
                    best_d = station
                    break
            
            if best_d is None:
                raise ValueError("No feasible station found")
            
            # Check if this station meets POI requirements
            poi_count = self.restaurant_finder.find_poi(
                poi_type, best_d,
                max_distance=max_distance,
                min_rating=min_rating
            )
            
            if poi_count >= min_count:
                # Feasible solution found!
                routes = {s: path_matrix[s][best_d] for s in start_stations}
                print(f"Found feasible station {best_d} with {poi_count} {poi_type}(s) (iteration {iteration})")
                return {
                    'destination': best_d,
                    'routes': routes,
                    'objective': objective,
                    'poi_constraint_met': True,
                    'poi_count': poi_count,
                    'iterations': iteration
                }
            
            # This station doesn't meet POI requirements, exclude it and retry
            print(f"Station {best_d} has only {poi_count} {poi_type}(s), excluding and retrying...")
            excluded_stations.add(best_d)
        
        raise ValueError(
            f"Could not find station satisfying all constraints "
            f"(checked {max_iterations} stations, "
            f"required: {min_count} {poi_type}(s) rated >= {min_rating})"
        )

    def _build_optimization_model(self, start_stations, time_matrix, objective, excluded_stations=None):
        """
        Build a Gurobi optimization model for the meeting point problem.
        
        Args:
            start_stations: List of starting station IDs
            time_matrix: Dict mapping (source, dest) to travel time
            objective: 'total_time' or 'variance'
            excluded_stations: Set of stations to exclude from consideration
            
        Returns:
            A Gurobi model ready to optimize
        """
        if excluded_stations is None:
            excluded_stations = set()
        
        model = gp.Model("meetup_optimization")
        model.setParam('OutputFlag', 0)
        
        # Decision variables: d[station] = 1 if this is the meeting station
        d_vars = model.addVars(self.all_stations, vtype=gp.GRB.BINARY, name="d")
        
        # Exactly one station must be chosen
        model.addConstr(gp.quicksum(d_vars[d] for d in self.all_stations) == 1)
        
        # Exclude stations that didn't meet previous constraints
        for excluded in excluded_stations:
            model.addConstr(d_vars[excluded] == 0)
        
        # Exclude closed stations from being chosen as destination
        for closed_station in self.closed_stations:
            if closed_station in self.all_stations:
                model.addConstr(d_vars[closed_station] == 0)
        
        # Set objective based on optimization type
        if objective == 'total_time':
            obj = gp.quicksum(
                time_matrix[s][d] * d_vars[d]
                for s in start_stations
                for d in self.all_stations
                if time_matrix[s][d] < float('inf')
            )
            model.setObjective(obj, gp.GRB.MINIMIZE)
        elif objective == 'variance':
            t_vars = model.addVars(start_stations, name="t")
            for s in start_stations:
                model.addConstr(
                    t_vars[s] == gp.quicksum(
                        time_matrix[s][d] * d_vars[d]
                        for d in self.all_stations
                        if time_matrix[s][d] < float('inf')
                    )
                )
            sum_t = gp.quicksum(t_vars[s] for s in start_stations)
            sum_t2 = gp.quicksum(t_vars[s] * t_vars[s] for s in start_stations)
            n = len(start_stations)
            obj = (1/n) * sum_t2 - (1/(n**2)) * sum_t * sum_t
            model.setObjective(obj, gp.GRB.MINIMIZE)
        else:
            raise ValueError(f"Unknown objective: {objective}")
        
        return model


if __name__ == "__main__":
    # Initialize optimizer
    optimizer = OptimizeRoute()
    
    print("=" * 80)
    print("TEST 1: Basic optimization without POI constraints")
    print("=" * 80)
    
    # Example 1: Two adjacent stations, minimize total time
    starts = ["940GZZLUHAW", "940GZZLUKEN"]  # Harrow & Wealdstone and Kenton
    result = optimizer.optimize(starts, objective='total_time')
    print(f"Starting stations: {starts}")
    print(f"Optimal meeting station (min total time): {result['destination']}")
    print(f"Routes: {result['routes']}\n")
    
    print("=" * 80)
    print("TEST 2: Basic optimization - minimize variance")
    print("=" * 80)
    
    # Same stations, minimize variance
    result = optimizer.optimize(starts, objective='variance')
    print(f"Starting stations: {starts}")
    print(f"Optimal meeting station (min variance): {result['destination']}")
    print(f"Routes: {result['routes']}\n")
    
    print("=" * 80)
    print("TEST 3: POI-constrained optimization (restaurants)")
    print("=" * 80)
    
    # Optimize with POI constraint
    poi_constraint = {
        'type': 'restaurant',
        'min_count': 5,
        'min_rating': 3.5,
        'max_distance': 750
    }
    result = optimizer.optimize(starts, objective='total_time', poi_constraint=poi_constraint)
    print(f"Starting stations: {starts}")
    print(f"Meeting station (min time + {poi_constraint}): {result['destination']}")
    print(f"Found {result.get('poi_count', 'N/A')} restaurants meeting criteria")
    print(f"Took {result.get('iterations', 'N/A')} iteration(s) to find feasible solution")
    print(f"Routes: {result['routes']}\n")
    
    print("=" * 80)
    print("TEST 4: POI-constrained optimization (pubs)")
    print("=" * 80)
    
    # Different POI constraint
    poi_constraint = {
        'type': 'pub',
        'min_count': 3,
        'min_rating': 3.0,
        'max_distance': 1000
    }
    result = optimizer.optimize(starts, objective='total_time', poi_constraint=poi_constraint)
    print(f"Starting stations: {starts}")
    print(f"Meeting station (min time + pubs): {result['destination']}")
    print(f"Found {result.get('poi_count', 'N/A')} pubs meeting criteria")
    print(f"Took {result.get('iterations', 'N/A')} iteration(s) to find feasible solution")
    print(f"Routes: {result['routes']}\n")
    
    print("=" * 80)
    print("TEST 5: Three-station group with POI constraint")
    print("=" * 80)
    
    # Larger group
    starts = ["940GZZLUWYP", "940GZZLUSTM", "940GZZLUCHX"]  # Wembley Park, Stanmore, Charing Cross
    poi_constraint = {
        'type': 'park',
        'min_count': 2,
        'min_rating': 3.0,
        'max_distance': 750
    }
    result = optimizer.optimize(starts, objective='variance', poi_constraint=poi_constraint)
    print(f"Starting stations: {starts}")
    print(f"Meeting station (min variance + parks): {result['destination']}")
    print(f"Found {result.get('poi_count', 'N/A')} parks meeting criteria\n")
    
    print("=" * 80)
    print("TEST 6: Single station edge case")
    print("=" * 80)
    
    # Edge case: single station
    starts = ["940GZZLUHAW"]  # Harrow & Wealdstone
    result = optimizer.optimize(starts, objective='total_time')
    print(f"Starting stations: {starts}")
    print(f"Optimal meeting station: {result['destination']}")
    print(f"Expected: destination should be the starting station itself")

