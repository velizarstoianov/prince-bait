class DuplicateRows(Exception):
    def __init__(self,message="Datatable has duplicate rows"):
        self.message = message
        super().__init__(self.message)
